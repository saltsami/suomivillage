"""
Ambient Event Collector Worker

Fetches external data (weather, news) and normalizes into ambient_events.
Currently uses mock data - swap fetchers to real APIs later.

Usage:
    python -m app.worker

Environment:
    DATABASE_URL - PostgreSQL connection string
    AMBIENT_REGION - Region for weather/news (default: Keski-Suomi)
    AMBIENT_POLL_SECONDS - Poll interval (default: 3600)
    AMBIENT_WEATHER_ENABLED - Enable weather fetch (default: 1)
    AMBIENT_NEWS_ENABLED - Enable news fetch (default: 1)
    AMBIENT_SPORTS_ENABLED - Enable sports fetch (default: 0)
"""

import asyncio
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL")
REGION = os.getenv("AMBIENT_REGION", "Keski-Suomi")
RUN_EVERY_SECONDS = int(os.getenv("AMBIENT_POLL_SECONDS", "3600"))  # 1h default
WEATHER_ENABLED = os.getenv("AMBIENT_WEATHER_ENABLED", "1") == "1"
NEWS_ENABLED = os.getenv("AMBIENT_NEWS_ENABLED", "1") == "1"
SPORTS_ENABLED = os.getenv("AMBIENT_SPORTS_ENABLED", "0") == "1"


def stable_id(prefix: str, sim_d: date, key: str) -> str:
    """Generate stable, deterministic ID for ambient events."""
    h = hashlib.sha256(f"{prefix}:{sim_d.isoformat()}:{key}".encode("utf-8")).hexdigest()[:8]
    return f"amb_{sim_d.strftime('%Y%m%d')}_{prefix}_{h}"


async def insert_source(conn: asyncpg.Connection, provider: str, region: str, request: dict, response: Any) -> int:
    """Store raw API response for replay."""
    row = await conn.fetchrow(
        """INSERT INTO ambient_sources(provider, region, request, response)
           VALUES ($1, $2, $3, $4) RETURNING id""",
        provider, region, json.dumps(request), json.dumps(response)
    )
    return int(row["id"])


async def upsert_ambient_event(conn: asyncpg.Connection, ev: dict) -> bool:
    """Insert or ignore ambient event (idempotent)."""
    result = await conn.execute(
        """INSERT INTO ambient_events(id, sim_date, type, region, topic, intensity, sentiment, confidence, expires_at, source_ref, payload)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
           ON CONFLICT (id) DO NOTHING""",
        ev["id"],
        ev["sim_date"],
        ev["type"],
        ev.get("region"),
        ev["topic"],
        ev["intensity"],
        ev["sentiment"],
        ev["confidence"],
        ev.get("expires_at"),
        json.dumps(ev["source_ref"]),
        json.dumps(ev["payload"])
    )
    return "INSERT" in result


# --- Mock Fetchers (swap these for real APIs) ---

MOCK_WEATHER_CONDITIONS = [
    {"condition": "snow", "summary_fi": "Lumisadetta ja pakkasta, tiet liukkaita.", "facts": ["Lunta sataa", "Liukasta paikoin", "-6°C"], "intensity": 0.8, "temp_c": -6, "sentiment": 0.1},
    {"condition": "rain", "summary_fi": "Vesisadetta koko päivän. Ota sateenvarjo.", "facts": ["Vettä sataa", "+8°C", "Tuulista"], "intensity": 0.5, "temp_c": 8, "sentiment": -0.2},
    {"condition": "sunny", "summary_fi": "Aurinkoinen päivä! Lämmintä tulossa.", "facts": ["Aurinko paistaa", "+18°C", "Heikko tuuli"], "intensity": 0.6, "temp_c": 18, "sentiment": 0.7},
    {"condition": "cloudy", "summary_fi": "Pilvistä mutta poutaa. Normaali syyspäivä.", "facts": ["Pilvistä", "+12°C", "Ei sadetta"], "intensity": 0.3, "temp_c": 12, "sentiment": 0.0},
    {"condition": "storm", "summary_fi": "Myrsky lähestyy! Pysy sisällä jos mahdollista.", "facts": ["Kova tuuli", "Ukkosta", "Rankkasateita"], "intensity": 0.9, "temp_c": 14, "sentiment": -0.5},
]

MOCK_NEWS_ITEMS = [
    {"headline": "Hallitus neuvottelee budjetista - leikkaukset puhuttavat", "facts": ["Neuvottelut jatkuvat", "Eri linjauksia"], "category": "suomi"},
    {"headline": "Myrsky aiheutti sähkökatkoja - korjaustyöt käynnissä", "facts": ["Katkoksia alueittain", "Korjaustyöt käynnissä"], "category": "suomi"},
    {"headline": "Uusi tutkimus: kahvi pidentää elinikää", "facts": ["Tutkimus julkaistu", "3-4 kuppia päivässä optimaalista"], "category": "terveys"},
    {"headline": "Bensan hinta nousussa - tankkaa nyt", "facts": ["Hinta noussut 5%", "Nousu jatkuu"], "category": "talous"},
    {"headline": "Kesälomakausi alkaa - ruuhkia odotettavissa", "facts": ["Liikenne vilkastuu", "Mökkeille matkaa"], "category": "suomi"},
    {"headline": "Kuntavaalit lähestyvät - ehdokkaat aktivoituvat", "facts": ["Kampanjat käynnissä", "Äänestys kesäkuussa"], "category": "politiikka"},
    {"headline": "Työttömyys laskee - avoimia paikkoja enemmän", "facts": ["Työttömyys 6.2%", "Kasvua näkyvissä"], "category": "talous"},
    {"headline": "Uusi ravintola avautuu keskustaan", "facts": ["Avajaiset lauantaina", "Suomalaista lähiruokaa"], "category": "paikallinen"},
]

MOCK_SPORTS_ITEMS = [
    {"headline": "Leijonat voittoon MM-kisoissa!", "facts": ["Suomi voitti 4-2", "Välieriin"], "category": "jääkiekko", "intensity": 0.9, "sentiment": 0.8},
    {"headline": "HJK varmisti mestaruuden", "facts": ["5. peräkkäinen mestaruus", "Kausi ohi"], "category": "jalkapallo", "intensity": 0.7, "sentiment": 0.6},
    {"headline": "Suomen hiihtomaajoukkue valmistautuu kauteen", "facts": ["Leirit alkaneet", "Uusia nimiä mukana"], "category": "hiihto", "intensity": 0.4, "sentiment": 0.3},
]


async def fetch_weather_mock(sim_d: date) -> dict:
    """Mock weather - varies by day deterministically."""
    import random
    rng = random.Random(sim_d.toordinal())
    return rng.choice(MOCK_WEATHER_CONDITIONS)


async def fetch_news_mock(sim_d: date, limit: int = 4) -> List[dict]:
    """Mock news headlines - varies by day deterministically."""
    import random
    rng = random.Random(sim_d.toordinal() + 1000)
    return rng.sample(MOCK_NEWS_ITEMS, min(limit, len(MOCK_NEWS_ITEMS)))


async def fetch_sports_mock(sim_d: date) -> List[dict]:
    """Mock sports headlines - rare events."""
    import random
    rng = random.Random(sim_d.toordinal() + 2000)
    # Only 30% chance of sports news on any given day
    if rng.random() < 0.3:
        return [rng.choice(MOCK_SPORTS_ITEMS)]
    return []


# --- Normalizers ---

def normalize_weather(sim_d: date, raw: dict, source_id: int) -> dict:
    """Convert raw weather to normalized ambient_event."""
    condition = raw.get("condition", "unknown")
    topic = f"weather_{condition}"
    ev_id = stable_id("weather", sim_d, f"{topic}:{raw.get('temp_c')}")
    expires = datetime.now(timezone.utc) + timedelta(hours=12)
    return {
        "id": ev_id,
        "sim_date": sim_d,
        "type": "AMBIENT_WEATHER",
        "region": REGION,
        "topic": topic,
        "intensity": float(raw.get("intensity", 0.5)),
        "sentiment": float(raw.get("sentiment", 0.0)),
        "confidence": 0.95,
        "expires_at": expires,
        "source_ref": {"provider": "weather", "ambient_source_id": source_id, "raw_id": None},
        "payload": {
            "summary_fi": raw["summary_fi"],
            "facts": raw["facts"],
            "condition": condition,
            "temp_c": raw.get("temp_c"),
        }
    }


def normalize_news(sim_d: date, item: dict, source_id: int, idx: int) -> dict:
    """Convert raw news item to normalized ambient_event."""
    headline = item["headline"]
    ev_id = stable_id("news", sim_d, f"{headline}:{idx}")
    expires = datetime.now(timezone.utc) + timedelta(hours=18)
    category = item.get("category", "general")
    return {
        "id": ev_id,
        "sim_date": sim_d,
        "type": "AMBIENT_NEWS_HEADLINE",
        "region": REGION,
        "topic": f"news_{category}",
        "intensity": 0.6,
        "sentiment": 0.0,
        "confidence": 0.8,
        "expires_at": expires,
        "source_ref": {"provider": "news", "ambient_source_id": source_id, "raw_id": None},
        "payload": {
            "headline": headline,
            "summary_fi": headline,
            "facts": item.get("facts", [])[:3],
            "category": category
        }
    }


def normalize_sports(sim_d: date, item: dict, source_id: int, idx: int) -> dict:
    """Convert raw sports item to normalized ambient_event."""
    headline = item["headline"]
    ev_id = stable_id("sports", sim_d, f"{headline}:{idx}")
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    category = item.get("category", "urheilu")
    return {
        "id": ev_id,
        "sim_date": sim_d,
        "type": "AMBIENT_SPORTS_HEADLINE",
        "region": REGION,
        "topic": f"sports_{category}",
        "intensity": float(item.get("intensity", 0.5)),
        "sentiment": float(item.get("sentiment", 0.3)),
        "confidence": 0.9,
        "expires_at": expires,
        "source_ref": {"provider": "sports", "ambient_source_id": source_id, "raw_id": None},
        "payload": {
            "headline": headline,
            "summary_fi": headline,
            "facts": item.get("facts", [])[:3],
            "category": category
        }
    }


# --- Main Collection Loop ---

async def run_once(pool: asyncpg.Pool) -> Dict[str, int]:
    """Run one collection cycle. Returns counts of inserted events."""
    sim_d = datetime.now(timezone.utc).date()
    counts = {"weather": 0, "news": 0, "sports": 0}

    async with pool.acquire() as conn:
        # Weather
        if WEATHER_ENABLED:
            raw = await fetch_weather_mock(sim_d)
            src_id = await insert_source(conn, "weather", REGION, {"mode": "mock", "date": sim_d.isoformat()}, raw)
            ev = normalize_weather(sim_d, raw, src_id)
            if await upsert_ambient_event(conn, ev):
                counts["weather"] += 1
                print(f"[ambient] inserted weather: {ev['topic']} ({ev['payload']['summary_fi'][:40]}...)")

        # News
        if NEWS_ENABLED:
            items = await fetch_news_mock(sim_d)
            src_id = await insert_source(conn, "news", REGION, {"mode": "mock", "limit": len(items)}, items)
            for i, item in enumerate(items[:6]):
                ev = normalize_news(sim_d, item, src_id, i)
                if await upsert_ambient_event(conn, ev):
                    counts["news"] += 1
                    print(f"[ambient] inserted news: {ev['payload']['headline'][:50]}...")

        # Sports
        if SPORTS_ENABLED:
            items = await fetch_sports_mock(sim_d)
            if items:
                src_id = await insert_source(conn, "sports", REGION, {"mode": "mock"}, items)
                for i, item in enumerate(items[:3]):
                    ev = normalize_sports(sim_d, item, src_id, i)
                    if await upsert_ambient_event(conn, ev):
                        counts["sports"] += 1
                        print(f"[ambient] inserted sports: {ev['payload']['headline'][:50]}...")

    return counts


async def main() -> None:
    """Main loop - runs collection on interval."""
    print(f"[ambient_worker] starting (region={REGION}, poll_seconds={RUN_EVERY_SECONDS})")
    print(f"[ambient_worker] enabled: weather={WEATHER_ENABLED}, news={NEWS_ENABLED}, sports={SPORTS_ENABLED}")

    pool = await asyncpg.create_pool(DATABASE_URL)

    try:
        while True:
            try:
                counts = await run_once(pool)
                total = sum(counts.values())
                if total > 0:
                    print(f"[ambient_worker] cycle complete: {counts}")
                else:
                    print(f"[ambient_worker] cycle complete: no new events (already exist)")
            except Exception as e:
                print(f"[ambient_worker] error: {e}")

            await asyncio.sleep(RUN_EVERY_SECONDS)
    finally:
        await pool.close()
        print("[ambient_worker] stopped")


if __name__ == "__main__":
    asyncio.run(main())
