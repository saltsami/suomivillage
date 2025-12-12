import asyncio
import json
from typing import Any, Dict

import asyncpg
import httpx
from redis.asyncio import Redis

from packages.shared.settings import Settings

settings = Settings()
redis_client: Redis | None = None
db_pool: asyncpg.Pool | None = None
http_client = httpx.AsyncClient(timeout=30.0)


async def init_services() -> None:
    global redis_client, db_pool
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    db_pool = await asyncpg.create_pool(settings.database_url)


async def close_services() -> None:
    if redis_client:
        await redis_client.close()
    if db_pool:
        await db_pool.close()
    await http_client.aclose()


async def fetch_job() -> Dict[str, Any] | None:
    assert redis_client is not None
    _, job_json = await redis_client.brpop(settings.render_queue)
    return json.loads(job_json)


async def call_gateway(job: Dict[str, Any]) -> Dict[str, Any]:
    prompt_context = job.get("prompt_context", {})
    event = prompt_context.get("event", {})
    summary = prompt_context.get("summary", "render this event")

    author_profile = None
    if db_pool:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT profile FROM npc_profiles WHERE npc_id=$1", job["author_id"])
            if row:
                author_profile = row["profile"]
                if isinstance(author_profile, str):
                    author_profile = json.loads(author_profile)

    prompt = summary
    if event:
        prompt = (
            f"Kirjoita {job['channel']}-julkaisu tapahtumasta.\n"
            f"Tyyppi: {event.get('type')}\n"
            f"Paikka: {event.get('place_id')}\n"
            f"Näyttelijät: {event.get('actors')}\n"
            f"Kohteet: {event.get('targets')}\n"
            f"Payload: {json.dumps(event.get('payload', {}), ensure_ascii=False)}"
        )

    payload = {
        "prompt": prompt,
        "channel": job["channel"],
        "author_id": job["author_id"],
        "source_event_id": job["source_event_id"],
        "context": {**prompt_context, "author_profile": author_profile},
        "temperature": job.get("temperature"),
    }
    response = await http_client.post(f"{settings.llm_gateway_url}/generate", json=payload)
    response.raise_for_status()
    return response.json()


async def persist_post(data: Dict[str, Any]) -> None:
    assert db_pool is not None
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO posts (channel, author_id, source_event_id, tone, text, tags, safety_notes)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            data["channel"],
            data["author_id"],
            data["source_event_id"],
            data["tone"],
            data["text"],
            json.dumps(data.get("tags", [])),
            data.get("safety_notes"),
        )


async def process_once() -> None:
    job = await fetch_job()
    generated = await call_gateway(job)
    await persist_post(generated)
    print(f"[worker] stored post for event {generated['source_event_id']}")


async def main() -> None:
    await init_services()
    print("[worker] started")
    try:
        while True:
            await process_once()
    except asyncio.CancelledError:
        pass
    finally:
        await close_services()
        print("[worker] stopped")


if __name__ == "__main__":
    asyncio.run(main())
