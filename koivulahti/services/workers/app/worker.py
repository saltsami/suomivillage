import asyncio
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Dict

import asyncpg
import httpx
from redis.asyncio import Redis

from packages.shared.settings import Settings


# --- Helper functions for deterministic variation and style extraction ---

def rng_for(event_id: str, author_id: str) -> random.Random:
    """Create deterministic RNG based on event+author for consistent variation."""
    h = hashlib.sha256(f"{event_id}:{author_id}".encode("utf-8")).hexdigest()
    seed = int(h[:8], 16)
    return random.Random(seed)


def style_from_profile(profile: dict, channel: str, event: dict) -> str:
    """Turn rich profile dict into short natural language style instructions."""
    if not profile:
        profile = {}

    name = profile.get("name", "Kyläläinen")
    bio = profile.get("bio", "")

    voice = profile.get("voice", {}) or {}
    if isinstance(voice, str):
        # Fallback if voice is string
        voice = {}

    # Extract voice parameters with defaults
    slang = voice.get("slang_level", 0.3)
    sarcasm = voice.get("sarcasm", 0.2)
    politeness = voice.get("politeness", 0.6)
    verbosity = voice.get("verbosity", 0.5)
    sigs = voice.get("signature_phrases", []) or []

    # Map numeric values to Finnish descriptions
    def lvl(x, low, high, a, b, c):
        return a if x < low else (b if x < high else c)

    slang_w = lvl(slang, 0.25, 0.6, "yleiskieltä", "rento puhekieli", "slangia")
    sarcasm_w = lvl(sarcasm, 0.2, 0.5, "", "pientä ironiaa", "sarkastinen")
    polite_w = lvl(politeness, 0.4, 0.75, "suorapuheinen", "asiallinen", "kohtelias")
    terse_w = lvl(verbosity, 0.35, 0.65, "tiivis", "napakka", "hieman laveampi")

    # Choose signature phrase rarely & deterministically
    r = rng_for(event.get("id", "evt"), profile.get("id", "npc"))
    sig = r.choice(sigs) if (sigs and channel in ("FEED", "CHAT") and r.random() < 0.3) else None

    if channel == "NEWS":
        return (
            "Kirjoita neutraali uutistyyli, 2–3 lausetta. "
            "Ei minä-muotoa. Ei mielipiteitä. Vain faktat."
        )

    # Build style string
    style_parts = [s for s in [slang_w, polite_w, sarcasm_w, terse_w] if s]
    style_str = ", ".join(style_parts)

    base = f"Olet {name}."
    if bio:
        base += f" {bio[:100]}"
    base += f" Tyyli: {style_str}. Max 2 lausetta, minä-muoto, ei meta-puhetta."

    if sig:
        base += f' Voit käyttää fraasia: "{sig}".'

    return base


def event_facts_fi(event: dict) -> str:
    """Extract concrete facts from event payload for better specificity."""
    t = event.get("type", "UNKNOWN")
    place = (event.get("place_id") or "place_kylä").replace("place_", "")
    payload = event.get("payload") or {}
    actors = event.get("actors", [])
    targets = event.get("targets", [])

    # Extract payload details
    topic = payload.get("topic")
    item = payload.get("item")
    mood = payload.get("mood")
    activity = payload.get("activity")
    satisfaction = payload.get("satisfaction")

    parts = []

    # Handle AMBIENT_SEEN events specially
    if t == "AMBIENT_SEEN":
        ambient_topic = payload.get("topic", "")
        summary = payload.get("summary_fi", "")
        facts = payload.get("facts", [])
        if ambient_topic:
            parts.append(f"aihe={ambient_topic}")
        if summary:
            parts.append(f"tilanne={summary[:60]}")
        if facts:
            parts.append(f"faktat=[{', '.join(facts[:2])}]")
        return ", ".join(parts) if parts else "ambient_event"

    # Handle POST_SEEN events (replies)
    if t == "POST_SEEN":
        original_text = payload.get("original_text", "")[:60]
        author_id = payload.get("author_id", "").replace("npc_", "").capitalize()
        reply_type = payload.get("reply_type", "neutral")
        parts.append(f"vastaus_tyyppi={reply_type}")
        parts.append(f"alkuperäinen_kirjoittaja={author_id}")
        parts.append(f"alkuperäinen_teksti={original_text}")
        return ", ".join(parts) if parts else "post_reply"

    # Regular events
    if place and place != "kylä":
        parts.append(f"paikka={place}")

    if t == "SMALL_TALK" and targets:
        target_name = targets[0].replace("npc_", "").capitalize()
        parts.append(f"juttelukumppani={target_name}")
    if topic:
        parts.append(f"aihe={topic}")
    if item:
        parts.append(f"asia={item}")
    if mood:
        parts.append(f"fiilis={mood}")
    if activity:
        parts.append(f"tekeminen={activity}")
    if satisfaction:
        parts.append(f"tunnelma={satisfaction}")

    return ", ".join(parts)

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


def make_draft(channel: str, event: Dict[str, Any], author_id: str, prompt_context: Dict[str, Any] = None) -> str:
    """Create a deterministic draft with variation based on event."""
    # Check if ambient draft is provided in prompt_context
    if prompt_context and prompt_context.get("draft"):
        return prompt_context["draft"]

    event_type = event.get("type", "UNKNOWN")
    event_id = event.get("id", "evt")
    place_id = event.get("place_id", "")
    place = place_id.replace("place_", "") if place_id else "kylällä"
    payload = event.get("payload") or {}

    # Deterministic RNG for this event+author combo
    r = rng_for(event_id, author_id)

    # Map place_id to Finnish location names
    place_names = {
        "kahvio": "kahviolla",
        "sauna": "saunassa",
        "kauppa": "kaupassa",
        "paja": "pajalla",
        "ranta": "rannalla",
        "kylatalo": "kylätalolla",
        "tori": "torilla",
    }
    place_fi = place_names.get(place, place + "ssa")

    # Extract payload details for richer drafts
    topic = payload.get("topic", "")
    item = payload.get("item", "")
    mood = payload.get("mood", "")
    activity = payload.get("activity", "")

    # --- LOCATION_VISIT ---
    if event_type == "LOCATION_VISIT":
        if channel == "FEED":
            opts = [
                f"Kävin {place_fi}. {activity or 'Teki hyvää.'}",
                f"Piipahdin {place_fi}. {mood or 'Ihan ok.'}",
                f"Poikkesin {place_fi}. {activity or 'Pieni tauko.'}",
            ]
        else:
            opts = [
                f"Oon {place_fi}. {activity or 'Chillaan.'}",
                f"Tulin {place_fi}. {mood or 'Mitäs täällä?'}",
                f"{place_fi.capitalize()} nyt. {activity or ''}",
            ]
        return r.choice(opts).strip()

    # --- SMALL_TALK ---
    elif event_type == "SMALL_TALK":
        targets = event.get("targets", [])
        topic_str = f" {topic}sta" if topic else ""
        mood_str = mood or ""

        if targets:
            target = targets[0].replace("npc_", "").capitalize()
            if channel == "FEED":
                opts = [
                    f"Juttelin {target}n kanssa{topic_str} {place_fi}. {mood_str}",
                    f"Törmäsin {target}iin {place_fi}. Vaihdettiin kuulumisia.{' ' + mood_str if mood_str else ''}",
                    f"Nähtiin {target}n kanssa {place_fi}.{' Puhuttiin ' + topic + '.' if topic else ''} {mood_str}",
                ]
            else:
                opts = [
                    f"Näin just {target}n {place_fi}. {mood_str or 'Mitäs sulle?'}",
                    f"Juttelin {target}n kaa. {mood_str}",
                    f"{target} oli {place_fi}. Vaihdettiin pari sanaa.",
                ]
        else:
            if channel == "FEED":
                opts = [
                    f"Kävin {place_fi}. {topic_str.strip() + ' oli puheenaiheena.' if topic else 'Mukavaa porukkaa.'}",
                    f"Istuskelin {place_fi}. {mood_str or 'Rauhallista.'}",
                    f"Viihdyin {place_fi}. {mood_str}",
                ]
            else:
                opts = [
                    f"Oon {place_fi}. {mood_str or 'Mitä kuuluu?'}",
                    f"Täällä {place_fi}. {topic_str.strip() + ' puhutaan.' if topic else ''}",
                    f"Istun {place_fi}. {mood_str}",
                ]
        return r.choice(opts).strip()

    # --- CUSTOMER_INTERACTION ---
    elif event_type == "CUSTOMER_INTERACTION":
        item_str = item or "asiakkaita"
        mood_str = mood or ""

        if channel == "FEED":
            opts = [
                f"Töissä {place_fi}. {item_str.capitalize()} tänään. {mood_str}",
                f"Palvelin {item_str} {place_fi}. {mood_str or 'Normi päivä.'}",
                f"Asiakkaita riitti {place_fi}. {mood_str}",
            ]
        else:
            opts = [
                f"Duunissa {place_fi}. {item_str.capitalize()}. {mood_str}",
                f"Hommia {place_fi}. {mood_str or 'Menee hyvin.'}",
                f"Täällä {place_fi} töissä. {item_str.capitalize() + '.' if item else ''}",
            ]
        return r.choice(opts).strip()

    # --- RUMOR_SPREAD ---
    elif event_type == "RUMOR_SPREAD":
        topic_str = topic or "juttuja"
        opts = [
            f"Kuulin {topic_str} {place_fi}. En tiedä mitä uskoa.",
            f"Kylällä puhutaan... {topic_str}. Mielenkiintoista.",
            f"Joku kertoi {topic_str}. Pitääkö paikkansa?",
        ]
        return r.choice(opts).strip()

    # --- AMBIENT_SEEN (fallback if no pre-written draft) ---
    elif event_type == "AMBIENT_SEEN":
        summary = payload.get("summary_fi", "")
        ambient_topic = payload.get("topic", "")
        if "weather" in ambient_topic:
            opts = [
                f"{summary[:50]}",
                f"Näin säätiedotuksen. {summary[:40]}",
            ]
        elif "news" in ambient_topic:
            opts = [
                f"Kuulin uutiset. {summary[:40]}",
                f"Uutisissa kerrottiin... {summary[:40]}",
            ]
        else:
            opts = [f"{summary[:50]}"]
        return r.choice(opts).strip()

    # --- POST_SEEN (reply to another post) ---
    elif event_type == "POST_SEEN":
        # Use draft from engine if provided, otherwise generate fallback
        if "draft" in payload and payload["draft"]:
            return payload["draft"]
        reply_type = payload.get("reply_type", "neutral")
        original_author = payload.get("author_id", "").replace("npc_", "").capitalize()
        original_text = payload.get("original_text", "")[:50]
        if reply_type == "question":
            opts = [f"@{original_author} Kerro lisää!", f"@{original_author} Mitä tarkoitat?"]
        elif reply_type in ["agree", "neutral"]:
            opts = [f"@{original_author} Niin on!", f"@{original_author} Jep."]
        elif reply_type in ["blame", "solution"]:
            opts = [f"@{original_author} Totta. Pitäisi tehdä jotain.", f"@{original_author} Sama mieltä."]
        elif reply_type == "worry":
            opts = [f"@{original_author} Huolestuttavaa.", f"@{original_author} Toivottavasti menee hyvin."]
        elif reply_type in ["invite", "joke"]:
            opts = [f"@{original_author} Mäkin tuun!", f"@{original_author} Haha!"]
        else:
            opts = [f"@{original_author} Joo.", f"@{original_author} Näin on."]
        return r.choice(opts).strip()

    # --- Fallback ---
    else:
        if channel == "FEED":
            return f"Kävin {place_fi}. {mood_str if mood else 'Ihan tavallinen päivä.'}"
        else:
            return f"Oon {place_fi}. {mood_str if mood else 'Mitäs?'}"


def build_prompt(channel: str, event: Dict[str, Any], author_profile: Dict[str, Any] | None, prompt_context: Dict[str, Any] = None) -> str:
    """Build draft-based prompt using style helpers - LLM rewrites draft in character voice."""
    author_id = (author_profile or {}).get("id", "npc")
    prompt_context = prompt_context or {}

    # Get style instructions from profile (handles dict voice properly)
    style = style_from_profile(author_profile, channel, event)

    # Get facts from event payload
    facts = event_facts_fi(event)

    # For ambient events, add ambient-specific facts
    if prompt_context.get("ambient_topic"):
        ambient_payload = prompt_context.get("ambient_payload", {})
        ambient_facts = ambient_payload.get("facts", [])
        if ambient_facts:
            facts += f", ambient_faktat=[{', '.join(ambient_facts)}]"

    # Create deterministic draft (uses ambient draft if provided)
    draft = make_draft(channel, event, author_id, prompt_context)

    if channel == "NEWS":
        return (
            f"{style}\n\n"
            f"FAKTAT: {facts}\n\n"
            f"Kirjoita lyhyt uutinen. Älä lisää mitään mitä faktoissa ei ole.\n"
            f"Vastaa vain uutistekstillä."
        )

    # FEED/CHAT: rewrite draft in character voice
    return (
        f"{style}\n\n"
        f"FAKTAT: {facts}\n"
        f"DRAFT (pidä faktat samana): {draft}\n\n"
        f"Tehtävä: muotoile draft uudelleen hahmon omalla äänellä. "
        f"Älä lisää uusia faktoja. Max 2 lausetta. Ei rivinvaihtoja.\n"
        f"Vastaa vain tekstillä."
    )


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
        prompt = build_prompt(job["channel"], event, author_profile, prompt_context)

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
            INSERT INTO posts (channel, author_id, source_event_id, tone, text, tags, safety_notes, parent_post_id, reply_type)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            data["channel"],
            data["author_id"],
            data["source_event_id"],
            data["tone"],
            data["text"],
            json.dumps(data.get("tags", [])),
            data.get("safety_notes"),
            data.get("parent_post_id"),  # NULL for non-replies
            data.get("reply_type"),  # NULL for non-replies
        )


async def process_once() -> None:
    job = await fetch_job()

    # Debug logging for author_id tracking
    job_author = job.get("author_id", "MISSING")
    job_channel = job.get("channel", "UNKNOWN")
    job_event = job.get("source_event_id", job.get("event_id", "UNKNOWN"))
    print(f"[worker] processing: author={job_author}, channel={job_channel}, event={job_event}")

    # Normalize event_id to source_event_id (engine uses event_id for POST_SEEN jobs)
    if "event_id" in job and "source_event_id" not in job:
        job["source_event_id"] = job["event_id"]

    generated = await call_gateway(job)

    # Verify author_id consistency
    gen_author = generated.get("author_id", "MISSING")
    if job_author != gen_author:
        print(f"[worker] WARNING: author_id mismatch! job={job_author} vs generated={gen_author}")

    # Merge reply fields from job (gateway doesn't know about these)
    if job.get("parent_post_id"):
        generated["parent_post_id"] = job["parent_post_id"]
    if job.get("reply_type"):
        generated["reply_type"] = job["reply_type"]

    await persist_post(generated)
    print(f"[worker] stored: author={gen_author}, event={generated['source_event_id']}")


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
