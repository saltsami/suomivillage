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


def make_draft(channel: str, event: Dict[str, Any], author_name: str) -> str:
    """Create a deterministic draft based on event - LLM will rewrite in character voice."""
    event_type = event.get("type", "UNKNOWN")
    place_id = event.get("place_id", "")
    place = place_id.replace("place_", "") if place_id else "kylällä"

    # Map place_id to Finnish location names
    place_names = {
        "kahvio": "kahviolla",
        "sauna": "saunassa",
        "kauppa": "kaupassa",
        "paja": "pajalla",
        "ranta": "rannalla",
        "kylatalo": "kylätalolla",
    }
    place_fi = place_names.get(place, place + "ssa")

    # Create simple draft based on event type
    if event_type == "LOCATION_VISIT":
        if channel == "FEED":
            return f"Kävin {place_fi}."
        else:  # CHAT
            return f"Oon nyt {place_fi}."

    elif event_type == "SMALL_TALK":
        targets = event.get("targets", [])
        if targets:
            target = targets[0].replace("npc_", "").capitalize()
            if channel == "FEED":
                return f"Juttelin {target}n kanssa {place_fi}."
            else:
                return f"Näin {target}n {place_fi}. Juteltiin hetki."
        else:
            if channel == "FEED":
                return f"Kävin {place_fi}. Oli mukavaa."
            else:
                return f"Oon {place_fi}. Mitä sulle kuuluu?"

    elif event_type == "CUSTOMER_INTERACTION":
        if channel == "FEED":
            return f"Asiakkaita {place_fi} tänään."
        else:
            return f"Töissä {place_fi}. Kiireistä."

    elif event_type == "RUMOR_SPREAD":
        return f"Kuulin juttuja {place_fi}. En tiedä mitä uskoa."

    else:
        # Generic fallback
        if channel == "FEED":
            return f"Tapahtui jotain {place_fi}."
        else:
            return f"Oon {place_fi} nyt."


def build_prompt(channel: str, event: Dict[str, Any], author_profile: Dict[str, Any] | None) -> str:
    """Build draft-based prompt - LLM rewrites draft in character voice."""

    # Get author info
    author_name = ""
    personality = ""
    voice = ""
    if author_profile:
        author_name = author_profile.get("name", "")
        personality = author_profile.get("personality", "")
        voice = author_profile.get("voice", "")

    # Create deterministic draft
    draft = make_draft(channel, event, author_name)

    # Build the rewrite prompt
    if channel == "NEWS":
        # NEWS is different - neutral style, not first person
        event_type = event.get("type", "UNKNOWN")
        place = event.get("place_id", "").replace("place_", "")
        actors = event.get("actors", [])
        actor_str = ", ".join([a.replace("npc_", "").capitalize() for a in actors[:2]]) if actors else "Kylän asukas"

        return (
            f"Kirjoita lyhyt uutisjuttu (max 2 lausetta, neutraali tyyli).\n\n"
            f"FAKTAT: {event_type} tapahtui paikassa {place}. Osallisena {actor_str}.\n\n"
            f"Kirjoita uutinen suomeksi:"
        )

    # FEED/CHAT: rewrite draft in character voice
    prompt = f"Kirjoita tämä uudelleen omalla tyylilläsi. 1. persoona, max 2 lausetta.\n\n"
    prompt += f"DRAFT: {draft}\n\n"

    if author_name:
        prompt += f"Olet {author_name}."
        if personality:
            prompt += f" Luonteesi: {personality}."
        if voice:
            prompt += f" Tyylisi: {voice}."
        prompt += "\n\n"

    if channel == "FEED":
        prompt += "Kirjoita somepostaus (rento, arkinen suomi):"
    else:
        prompt += "Kirjoita chat-viesti (lyhyt, keskusteleva):"

    return prompt


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
