import asyncio
import json
from pathlib import Path
from typing import Any, Dict

import asyncpg
import httpx
from redis.asyncio import Redis

from packages.shared.settings import Settings

settings = Settings()
redis_client: Redis | None = None
db_pool: asyncpg.Pool | None = None
http_client = httpx.AsyncClient(timeout=30.0)

# Load catalog prompts
# In Docker: /app/packages/shared/data/event_types.json
CATALOG_PATH = Path("/app/packages/shared/data/event_types.json")
if not CATALOG_PATH.exists():
    # Fallback for local dev
    CATALOG_PATH = Path(__file__).parent.parent.parent / "packages" / "shared" / "data" / "event_types.json"

with open(CATALOG_PATH) as f:
    catalog_data = json.load(f)
    PROMPT_CONFIG = catalog_data.get("content_generation_prompts", {})


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


def build_prompt(channel: str, event: Dict[str, Any], author_profile: Dict[str, Any] | None) -> str:
    """Build channel-specific prompt using catalog templates."""
    channel_key = f"{channel.lower()}_prompt"
    prompt_config = PROMPT_CONFIG.get(channel_key, {})
    system_msg = prompt_config.get("system", "")

    # Build event description in natural Finnish
    event_type = event.get("type", "UNKNOWN")
    place_id = event.get("place_id", "tuntematon paikka")
    actors = event.get("actors", [])
    targets = event.get("targets", [])
    payload = event.get("payload", {})

    # Create natural language description
    actor_names = ", ".join([a.replace("npc_", "").capitalize() for a in actors]) if actors else "joku"

    event_description = f"Tapahtuma: {event_type}"
    if place_id != "tuntematon paikka":
        event_description += f" paikassa {place_id.replace('place_', '')}"
    if actors:
        event_description += f". Osallistujat: {actor_names}"
    if targets:
        target_names = ", ".join([t.replace("npc_", "").capitalize() for t in targets])
        event_description += f". Kohteena: {target_names}"

    # Add payload details if meaningful
    if payload and isinstance(payload, dict):
        for key, value in payload.items():
            if key not in ["source", "tick"] and value:
                event_description += f". {key}: {value}"

    # Build user prompt with system context + event + profile
    user_prompt = f"{system_msg}\n\n"
    user_prompt += f"Tapahtuman tiedot:\n{event_description}\n\n"

    if author_profile:
        name = author_profile.get("name", "")
        personality = author_profile.get("personality", "")
        voice = author_profile.get("voice", "")
        if name:
            user_prompt += f"Hahmo: {name}\n"
        if personality:
            user_prompt += f"Luonne: {personality}\n"
        if voice:
            user_prompt += f"Tyyli: {voice}\n"
        user_prompt += "\n"

    # Add output instruction
    if channel == "FEED":
        user_prompt += "Kirjoita lyhyt somepostaus (max 280 merkkiä) tästä tapahtumasta hahmon näkökulmasta suomeksi. Ole luonnollinen ja inhimillinen."
    elif channel == "CHAT":
        user_prompt += "Kirjoita lyhyt chat-viesti (max 220 merkkiä) suomeksi. Ole reagoiva ja keskusteleva."
    elif channel == "NEWS":
        user_prompt += "Kirjoita lyhyt uutisotsikko ja tiivistelmä (max 480 merkkiä) neutraalisti suomeksi."
    else:
        user_prompt += f"Kirjoita lyhyt {channel}-julkaisu suomeksi."

    return user_prompt


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

    # Use catalog-based prompt building
    prompt = summary
    if event:
        prompt = build_prompt(job["channel"], event, author_profile)

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
