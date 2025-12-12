import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import asyncpg
from redis.asyncio import Redis

from packages.shared.data_loader import (
    get_day1_seed_events,
    get_event_types,
    get_impact_scoring_config,
    get_npc_profiles,
    get_places,
    get_relationship_edges,
)
from packages.shared.schemas import EventTypeItem
from packages.shared.settings import Settings

settings = Settings()
redis_client: Redis | None = None
db_pool: asyncpg.Pool | None = None
impact_config = get_impact_scoring_config()

DEFAULT_IMPACT_WEIGHTS: Dict[str, float] = {
    "novelty": 0.30,
    "conflict": 0.25,
    "publicness": 0.20,
    "status_of_people": 0.15,
    "cascade_potential": 0.10,
}


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


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def parse_sim_ts(event: Dict[str, Any]) -> datetime:
    ts_local_str = event.get("ts_local")
    sim_ts = datetime.now(tz=timezone.utc)
    if ts_local_str:
        try:
            parsed = datetime.fromisoformat(ts_local_str.replace("Z", "+00:00"))
            sim_ts = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            sim_ts = datetime.now(tz=timezone.utc)
    return sim_ts


async def fetch_npc_status(npc_ids: List[str], conn: asyncpg.Connection) -> float:
    if not npc_ids:
        return 0.5
    rows = await conn.fetch(
        "SELECT npc_id, profile FROM npc_profiles WHERE npc_id = ANY($1::text[])",
        npc_ids,
    )
    statuses: List[float] = []
    for row in rows:
        profile = row["profile"]
        if isinstance(profile, str):
            try:
                profile = json.loads(profile)
            except json.JSONDecodeError:
                profile = {}
        if isinstance(profile, dict):
            values = profile.get("values", {}) or {}
            status_val = values.get("status")
            if status_val is not None:
                try:
                    statuses.append(float(status_val))
                except (TypeError, ValueError):
                    pass
    if not statuses:
        return 0.5
    return clamp01(sum(statuses) / len(statuses))


async def compute_impact(
    event: Dict[str, Any],
    sim_ts: datetime,
    event_type: Optional[EventTypeItem],
    conn: asyncpg.Connection,
) -> float:
    publicness = clamp01(float(event.get("publicness", 0.0)))
    severity = clamp01(float(event.get("severity", 0.0)))
    conflict = severity

    window_start = sim_ts - timedelta(hours=24)
    recent_same_type = await conn.fetchval(
        """
        SELECT COUNT(*)
        FROM events
        WHERE type=$1 AND sim_ts >= $2 AND sim_ts < $3
        """,
        event["type"],
        window_start,
        sim_ts,
    )
    novelty = clamp01(1.0 / (1.0 + float(recent_same_type or 0)))

    actors = [a for a in event.get("actors", []) if isinstance(a, str) and a.startswith("npc_")]
    targets = [t for t in event.get("targets", []) if isinstance(t, str) and t.startswith("npc_")]
    status_of_people = await fetch_npc_status(sorted(set(actors + targets)), conn)

    cascade_potential = 0.0
    if event_type and isinstance(event_type.effects, dict):
        deltas = event_type.effects.get("relationship_deltas", []) or []
        rep_delta = float(event_type.effects.get("reputation_delta", 0.0) or 0.0)
        cascade_potential = (
            0.2 * severity
            + 0.15 * len(deltas)
            + 0.1 * min(1.0, abs(rep_delta) * 5.0)
            + 0.05 * len(targets)
        )
    cascade_potential = clamp01(cascade_potential)

    weights = dict(DEFAULT_IMPACT_WEIGHTS)
    weights.update(impact_config.get("weights", {}) or {})

    impact = (
        weights["novelty"] * novelty
        + weights["conflict"] * conflict
        + weights["publicness"] * publicness
        + weights["status_of_people"] * status_of_people
        + weights["cascade_potential"] * cascade_potential
    )
    return clamp01(impact)


def thresholds_by_channel() -> Dict[str, float]:
    return {
        "FEED": settings.impact_threshold_feed,
        "CHAT": settings.impact_threshold_chat,
        "NEWS": settings.impact_threshold_news,
    }


async def insert_event(event: Dict[str, Any], sim_ts: datetime, conn: asyncpg.Connection) -> bool:
    status = await conn.execute(
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
    try:
        return status.split()[-1] == "1"
    except Exception:
        return False


async def apply_event_effects(
    event: Dict[str, Any],
    sim_ts: datetime,
    event_type: Optional[EventTypeItem],
    conn: asyncpg.Connection,
) -> None:
    if not event_type or not isinstance(event_type.effects, dict):
        return

    effects = event_type.effects
    importance_base = float(effects.get("memory_importance_base", 0.1) or 0.1)
    relationship_deltas = effects.get("relationship_deltas", []) or []

    actors = [a for a in event.get("actors", []) if isinstance(a, str) and a.startswith("npc_")]
    targets = [t for t in event.get("targets", []) if isinstance(t, str) and t.startswith("npc_")]
    involved = sorted(set(actors + targets))

    summary = f"{event['type']} @ {event.get('place_id')}"
    for npc_id in involved:
        await conn.execute(
            """
            INSERT INTO memories (npc_id, event_id, importance, summary)
            VALUES ($1, $2, $3, $4)
            """,
            npc_id,
            event["id"],
            importance_base,
            summary,
        )

    if not relationship_deltas or not actors or not targets:
        return

    for actor in actors:
        for target in targets:
            if actor == target:
                continue
            await conn.execute(
                "INSERT INTO relationships (from_npc, to_npc) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                actor,
                target,
            )
            row = await conn.fetchrow(
                """
                SELECT trust, respect, affection, jealousy, fear, grievances
                FROM relationships
                WHERE from_npc=$1 AND to_npc=$2
                """,
                actor,
                target,
            )
            if not row:
                continue

            trust = int(row["trust"] or 0)
            respect = int(row["respect"] or 0)
            affection = int(row["affection"] or 0)
            jealousy = int(row["jealousy"] or 0)
            fear = int(row["fear"] or 0)
            grievances = row["grievances"]
            if isinstance(grievances, str):
                try:
                    grievances = json.loads(grievances)
                except json.JSONDecodeError:
                    grievances = []
            if not isinstance(grievances, list):
                grievances = []

            for delta in relationship_deltas:
                if not isinstance(delta, dict):
                    continue
                trust += int(delta.get("trust", 0) or 0)
                respect += int(delta.get("respect", 0) or 0)
                affection += int(delta.get("affection", 0) or 0)
                jealousy += int(delta.get("jealousy", 0) or 0)
                fear += int(delta.get("fear", 0) or 0)
                grievance = delta.get("grievance")
                if isinstance(grievance, str) and grievance:
                    grievances.append(grievance)
                if delta.get("grievance_soften") is True and grievances:
                    grievances.pop()

            await conn.execute(
                """
                UPDATE relationships
                SET trust=$3, respect=$4, affection=$5, jealousy=$6, fear=$7,
                    grievances=$8::jsonb, last_interaction_ts=$9
                WHERE from_npc=$1 AND to_npc=$2
                """,
                actor,
                target,
                trust,
                respect,
                affection,
                jealousy,
                fear,
                json.dumps(grievances),
                sim_ts,
            )


async def enqueue_render_jobs(
    event: Dict[str, Any],
    sim_ts: datetime,
    impact: float,
    event_type: Optional[EventTypeItem],
) -> None:
    assert redis_client is not None
    thresholds = thresholds_by_channel()
    channels: List[str] = []
    if event_type and isinstance(event_type.render, dict):
        channels = event_type.render.get("default_channels", []) or []

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
                "sim_ts": sim_ts.isoformat(),
            },
        }
        await redis_client.lpush(settings.render_queue, json.dumps(job))


async def process_event(
    event: Dict[str, Any],
    event_types: Dict[str, EventTypeItem],
) -> tuple[bool, datetime, float, Optional[EventTypeItem]]:
    assert db_pool is not None
    sim_ts = parse_sim_ts(event)
    event_type = event_types.get(event["type"])
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            inserted = await insert_event(event, sim_ts, conn)
            if not inserted:
                return False, sim_ts, 0.0, event_type
            await apply_event_effects(event, sim_ts, event_type, conn)
            impact = await compute_impact(event, sim_ts, event_type, conn)
            return True, sim_ts, impact, event_type


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

    event_types = {i.type: i for i in get_event_types()}
    for event in sorted(day1_events, key=lambda e: e.get("ts_local", "")):
        inserted, sim_ts, impact, event_type = await process_event(event, event_types)
        if not inserted:
            continue
        await enqueue_render_jobs(event, sim_ts, impact, event_type)
        print(f"[engine] injected {event['id']} ({event['type']}) impact={impact:.2f}")


async def fetch_latest_sim_ts() -> datetime:
    assert db_pool is not None
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT MAX(sim_ts) AS sim_ts FROM events")
        if row and row["sim_ts"]:
            return row["sim_ts"]
    return datetime.now(tz=timezone.utc)


ROUTINE_EVENT_TEMPLATES = [
    {
        "type": "LOCATION_VISIT",
        "place_types": ["sauna", "beach"],
        "publicness": 0.3,
        "severity": 0.0,
    },
    {
        "type": "SMALL_TALK",
        "place_types": ["cafe", "kahvio"],
        "publicness": 0.5,
        "severity": 0.0,
    },
    {
        "type": "CUSTOMER_INTERACTION",
        "place_types": ["shop", "store", "kahvio"],
        "publicness": 0.4,
        "severity": 0.0,
    },
]


async def generate_routine_event(
    tick_index: int,
    sim_ts: datetime,
    rng: random.Random,
) -> Optional[Dict[str, Any]]:
    """Generate a routine event deterministically based on tick index."""
    # Generate 1 event every ~10 ticks (adjustable)
    if tick_index % 10 != 0:
        return None

    npcs = get_npc_profiles()
    places = get_places()
    if not npcs or not places:
        return None

    # Select NPC deterministically using tick index
    npc_idx = (tick_index // 10) % len(npcs)
    npc = npcs[npc_idx]

    # Select routine template using RNG
    template = rng.choice(ROUTINE_EVENT_TEMPLATES)

    # Find a place matching the template's place_types
    matching_places = [
        p for p in places
        if any(pt in p.type.lower() for pt in template["place_types"])
    ]
    if not matching_places:
        matching_places = places

    place = rng.choice(matching_places)

    # Generate event ID
    event_id = f"evt_routine_{tick_index}_{npc.id}"

    return {
        "id": event_id,
        "type": template["type"],
        "place_id": place.id,
        "actors": [npc.id],
        "targets": [],
        "publicness": template["publicness"],
        "severity": template["severity"],
        "ts_local": sim_ts.isoformat(),
        "payload": {
            "source": "routine_injector",
            "tick": tick_index,
        },
    }


async def tick_once(
    sim_ts: datetime,
    tick_index: int,
    rng: random.Random,
    event_types: Dict[str, EventTypeItem],
) -> datetime:
    # Generate routine events for post-Day1 simulation
    if tick_index > 0:
        routine_event = await generate_routine_event(tick_index, sim_ts, rng)
        if routine_event:
            inserted, event_sim_ts, impact, event_type = await process_event(
                routine_event, event_types
            )
            if inserted:
                await enqueue_render_jobs(routine_event, event_sim_ts, impact, event_type)
                print(
                    f"[engine] injected {routine_event['id']} "
                    f"({routine_event['type']}) impact={impact:.2f}"
                )

    if tick_index % 60 == 0:
        print(f"[engine] tick {tick_index} sim_ts={sim_ts.isoformat()}")

    return sim_ts + timedelta(milliseconds=max(1, settings.sim_tick_ms))


async def main() -> None:
    await init_services()
    print("[engine] starting")
    try:
        await seed_db_if_empty()
        await inject_day1_events()
        event_types = {i.type: i for i in get_event_types()}
        rng = random.Random(settings.sim_seed)
        sim_ts = await fetch_latest_sim_ts()
        print(
            f"[engine] sim clock start sim_ts={sim_ts.isoformat()} seed={settings.sim_seed} tick_ms={settings.sim_tick_ms}"
        )

        tick_index = 0
        while True:
            sim_ts = await tick_once(sim_ts, tick_index, rng, event_types)
            tick_index += 1
            await asyncio.sleep(settings.sim_tick_ms / 1000.0)
    finally:
        await close_services()
        print("[engine] stopped")


if __name__ == "__main__":
    asyncio.run(main())
