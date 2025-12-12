import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import asyncpg
from redis.asyncio import Redis

from packages.shared.data_loader import (
    get_day1_seed_events,
    get_event_types,
    get_npc_profiles,
    get_places,
    get_relationship_edges,
)
from packages.shared.settings import Settings

settings = Settings()
redis_client: Redis | None = None
db_pool: asyncpg.Pool | None = None


async def init_services() -> None:
    global redis_client, db_pool
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    db_pool = await asyncpg.create_pool(settings.database_url)


async def close_services() -> None:
    if redis_client:
        await redis_client.aclose()
    if db_pool:
        await db_pool.close()


async def seed_db_if_empty() -> None:
    assert db_pool is not None
    places = get_places()
    npcs = get_npc_profiles()
    edges = get_relationship_edges()
    async with db_pool.acquire() as conn:
        entity_count = await conn.fetchval("SELECT COUNT(*) FROM entities")
        if entity_count and int(entity_count) > 0:
            return

        await conn.executemany(
            "INSERT INTO entities (id, type, name, meta) VALUES ($1, $2, $3, $4::jsonb) ON CONFLICT DO NOTHING",
            [(p.id, "place", p.name, json.dumps({"place_type": p.type})) for p in places],
        )
        await conn.executemany(
            "INSERT INTO entities (id, type, name, meta) VALUES ($1, $2, $3, $4::jsonb) ON CONFLICT DO NOTHING",
            [(n.id, "npc", n.name, json.dumps({"role": n.role, "archetypes": n.archetypes})) for n in npcs],
        )
        await conn.executemany(
            "INSERT INTO npc_profiles (npc_id, profile) VALUES ($1, $2::jsonb) ON CONFLICT DO NOTHING",
            [(n.id, json.dumps(n.model_dump())) for n in npcs],
        )
        await conn.executemany(
            """
            INSERT INTO relationships
              (from_npc, to_npc, mode, trust, respect, affection, jealousy, fear, grievances, debts)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb)
            ON CONFLICT DO NOTHING
            """,
            [
                (
                    e.from_npc,
                    e.to_npc,
                    e.mode,
                    e.trust,
                    e.respect,
                    e.affection,
                    e.jealousy,
                    e.fear,
                    json.dumps(e.grievances),
                    json.dumps(e.debts),
                )
                for e in edges
                if e.to_npc != "npc_all"
            ],
        )
        for n in npcs:
            for goal in n.goals_seed:
                await conn.execute(
                    """
                    INSERT INTO goals (npc_id, horizon, priority, goal_json)
                    VALUES ($1, $2, $3, $4::jsonb)
                    """,
                    n.id,
                    goal.get("horizon", "short"),
                    goal.get("priority", 0.5),
                    json.dumps(goal.get("goal", {})),
                )

    print(f"[engine] seeded {len(npcs)} NPCs and {len(places)} places")


def compute_impact(event: Dict[str, Any]) -> float:
    severity = float(event.get("severity", 0.0))
    publicness = float(event.get("publicness", 0.0))
    return 0.5 * severity + 0.5 * publicness


def thresholds_by_channel() -> Dict[str, float]:
    return {
        "FEED": settings.impact_threshold_feed,
        "CHAT": settings.impact_threshold_chat,
        "NEWS": settings.impact_threshold_news,
    }


async def insert_event(event: Dict[str, Any]) -> None:
    assert db_pool is not None
    ts_local_str = event.get("ts_local")
    sim_ts = datetime.now(tz=timezone.utc)
    if ts_local_str:
        try:
            parsed = datetime.fromisoformat(ts_local_str.replace("Z", "+00:00"))
            sim_ts = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            sim_ts = datetime.now(tz=timezone.utc)

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO events (id, sim_ts, place_id, type, actors, targets, publicness, severity, payload)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            event["id"],
            sim_ts,
            event.get("place_id"),
            event["type"],
            json.dumps(event.get("actors", [])),
            json.dumps(event.get("targets", [])),
            float(event.get("publicness", 0.0)),
            float(event.get("severity", 0.0)),
            json.dumps(event.get("payload", {})),
        )


async def enqueue_render_jobs(event: Dict[str, Any], event_type_channels: Dict[str, List[str]]) -> None:
    assert redis_client is not None
    impact = compute_impact(event)
    thresholds = thresholds_by_channel()
    channels = event_type_channels.get(event["type"], [])

    for channel in channels:
        if impact < thresholds.get(channel, 1.0):
            continue
        actors = event.get("actors", [])
        author_id = "npc_petri" if channel == "NEWS" else (actors[0] if actors else "npc_petri")
        job = {
            "channel": channel,
            "author_id": author_id,
            "source_event_id": event["id"],
            "prompt_context": {
                "summary": f"{event['type']} at {event.get('place_id')}",
                "event": event,
                "impact": impact,
            },
        }
        await redis_client.lpush(settings.render_queue, json.dumps(job))


async def inject_day1_events() -> None:
    assert db_pool is not None
    day1_events = get_day1_seed_events()
    if not day1_events:
        return

    async with db_pool.acquire() as conn:
        existing = await conn.fetchval("SELECT COUNT(*) FROM events")
        if existing and int(existing) > 0:
            print("[engine] events already present, skipping Day 1 seed")
            return

    event_type_channels = {i.type: i.render.get("default_channels", []) for i in get_event_types()}
    for event in sorted(day1_events, key=lambda e: e.get("ts_local", "")):
        await insert_event(event)
        await enqueue_render_jobs(event, event_type_channels)
        print(f"[engine] injected {event['id']} ({event['type']})")


async def main() -> None:
    await init_services()
    print("[engine] starting")
    try:
        await seed_db_if_empty()
        await inject_day1_events()
        print("[engine] idle (stub)")
        while True:
            await asyncio.sleep(3600)
    finally:
        await close_services()
        print("[engine] stopped")


if __name__ == "__main__":
    asyncio.run(main())
