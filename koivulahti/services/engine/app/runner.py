import asyncio
import hashlib
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


async def fetch_latest_tick_index() -> int:
    """Fetch the highest tick index from existing routine events to resume from."""
    assert db_pool is not None
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT MAX(CAST(SUBSTRING(id FROM 'evt_routine_(\\d+)_') AS INTEGER)) AS max_tick
            FROM events
            WHERE id LIKE 'evt_routine_%'
            """
        )
        if row and row["max_tick"] is not None:
            return int(row["max_tick"])
    return 0


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

# Rich payload content for routine events
PAYLOAD_OPTIONS = {
    "LOCATION_VISIT": {
        "activities": [
            "rentoutumassa", "tapaamassa tuttuja", "vain käymässä",
            "nauttimassa rauhasta", "hakemassa inspiraatiota", "tauolla",
        ],
        "moods": [
            "Teki hyvää.", "Rauhoittavaa.", "Ihan ok.", "Pieni irtiotto.",
            "Hyvä fiilis.", "Tarvitsin tätä.", "Virkistävää.",
        ],
    },
    "SMALL_TALK": {
        "topics": [
            "sää", "talkoot", "kyläjuorut", "työ", "perhe", "kesäsuunnitelmat",
            "naapurit", "kaupan tarjoukset", "kylän tapahtumat", "politiikka",
        ],
        "moods": [
            "Mukava hetki.", "Kuulin uutta.", "Vaihdettiin kuulumisia.",
            "Oli hauska jutella.", "Mielenkiintoista.", "Ihan perus.",
        ],
    },
    "CUSTOMER_INTERACTION": {
        "items": [
            "kahvia", "leipää", "maitoa", "sanomalehden", "postia",
            "perunoita", "kalaa", "juustoa", "makeisia", "tarvikkeita",
        ],
        "moods": [
            "Kiireinen päivä.", "Rauhallista tänään.", "Asiakkaita riitti.",
            "Normi päivä.", "Hyvin sujui.", "Paljon kyselijöitä.",
        ],
    },
}


# --- Ambient Event Distributor & Appraisal ---

# Visibility percentage for ambient event delivery (hash-based determinism)
DEFAULT_VISIBILITY_PCT = 60  # 60% of NPCs will "see" each ambient event

# Appraisal matrix: topic pattern -> archetype -> (intent, draft_template)
# Intents: POST_FEED, POST_CHAT, IGNORE, REPLY
APPRAISAL_MATRIX: Dict[str, Dict[str, tuple]] = {
    "weather_snow": {
        "romantic": ("POST_FEED", "Lunta sataa. Onpa kaunista ulkona."),
        "practical": ("POST_FEED", "Ja taas lumityöt. Ei voi mitään."),
        "anxious": ("POST_CHAT", "Liukasta on. Varokaa teillä!"),
        "stoic": ("IGNORE", None),
        "gossip": ("POST_CHAT", "Kuulin että lumimyrsky tulossa? Mitäs muut?"),
        "default": ("POST_FEED", "Lunta sataa. Talvi täällä."),
    },
    "weather_rain": {
        "romantic": ("POST_FEED", "Sade on melankolista. Kaunista silti."),
        "practical": ("POST_FEED", "Vesisadetta. Sateenvarjo mukaan."),
        "anxious": ("POST_CHAT", "Vettä tulee. Onkohan kaikilla kumisaappaat?"),
        "stoic": ("IGNORE", None),
        "default": ("POST_FEED", "Sataa vettä. Normaali päivä."),
    },
    "weather_sunny": {
        "romantic": ("POST_FEED", "Aurinko paistaa! Kaunis päivä edessä."),
        "practical": ("POST_FEED", "Hyvä keli. Hommiin vaan."),
        "social": ("POST_CHAT", "Onpa keli! Mennäänkö ulos?"),
        "stoic": ("IGNORE", None),
        "default": ("POST_FEED", "Aurinkoista. Hyvä päivä."),
    },
    "weather_storm": {
        "anxious": ("POST_CHAT", "Myrsky tulossa! Olkaa varovaisia!"),
        "practical": ("POST_FEED", "Myrsky lähestyy. Kannattaa pysyä sisällä."),
        "stoic": ("POST_FEED", "Myrsky menee ohi. Ei hätää."),
        "default": ("POST_FEED", "Myrsky tulossa. Varautukaa."),
    },
    "news_suomi": {
        "political": ("POST_FEED", "Taas näitä päätöksiä. Mitähän seuraavaksi."),
        "gossip": ("POST_CHAT", "Kuulitteko uutiset? Mitä mieltä olette?"),
        "anxious": ("POST_CHAT", "Huolestuttavia uutisia. Toivottavasti menee hyvin."),
        "stoic": ("IGNORE", None),
        "default": ("IGNORE", None),
    },
    "news_talous": {
        "practical": ("POST_FEED", "Talous taas otsikoissa. Katsotaan miten käy."),
        "anxious": ("POST_CHAT", "Hinnat nousee. Miten te selviätte?"),
        "stoic": ("IGNORE", None),
        "default": ("IGNORE", None),
    },
    "news_paikallinen": {
        "social": ("POST_FEED", "Kuulin paikallisia uutisia. Mielenkiintoista!"),
        "gossip": ("POST_CHAT", "Arvatkaa mitä kuulin! Kylällä tapahtuu."),
        "default": ("POST_FEED", "Paikkakunnalla tapahtuu."),
    },
    "sports_jääkiekko": {
        "social": ("POST_FEED", "Leijonat pelasi! Hyvä Suomi!"),
        "stoic": ("IGNORE", None),
        "default": ("POST_CHAT", "Näittekö pelin? Meni hyvin!"),
    },
    "sports_jalkapallo": {
        "social": ("POST_CHAT", "Hyvä peli! Mitä tykkäsitte?"),
        "default": ("IGNORE", None),
    },
}

# NPC post cooldowns (in-memory, reset on restart)
# Structure: {npc_id: {channel: last_post_datetime}}
_npc_cooldowns: Dict[str, Dict[str, datetime]] = {}

# Cooldown durations per channel (seconds)
COOLDOWN_SECONDS = {
    "FEED": 7200,   # 2 hours
    "CHAT": 1800,   # 30 min
    "NEWS": 86400,  # 1 day
}


def should_deliver_ambient(ambient_id: str, npc_id: str, visibility_pct: int = DEFAULT_VISIBILITY_PCT) -> bool:
    """Deterministic check if NPC should 'see' this ambient event."""
    h = hashlib.sha256(f"{ambient_id}:{npc_id}".encode()).hexdigest()
    return (int(h[:8], 16) % 100) < visibility_pct


def get_npc_archetype(npc_profile: Dict[str, Any]) -> str:
    """Extract primary archetype from NPC profile."""
    archetypes = npc_profile.get("archetypes", [])
    if archetypes:
        return archetypes[0].lower()
    return "default"


def appraise_ambient(topic: str, npc_profile: Dict[str, Any]) -> tuple:
    """Determine NPC's intent based on topic and personality. Returns (intent, draft)."""
    archetype = get_npc_archetype(npc_profile)

    # Try exact topic match first
    if topic in APPRAISAL_MATRIX:
        topic_responses = APPRAISAL_MATRIX[topic]
        if archetype in topic_responses:
            return topic_responses[archetype]
        if "default" in topic_responses:
            return topic_responses["default"]

    # Try prefix match (e.g., "weather_" for any weather)
    for pattern, responses in APPRAISAL_MATRIX.items():
        if topic.startswith(pattern.rsplit("_", 1)[0] + "_"):
            if archetype in responses:
                return responses[archetype]
            if "default" in responses:
                return responses["default"]

    return ("IGNORE", None)


def check_cooldown(npc_id: str, channel: str, now: datetime) -> bool:
    """Check if NPC can post to channel (not in cooldown). Returns True if allowed."""
    if npc_id not in _npc_cooldowns:
        return True
    if channel not in _npc_cooldowns[npc_id]:
        return True

    last_post = _npc_cooldowns[npc_id][channel]
    cooldown = COOLDOWN_SECONDS.get(channel, 3600)
    return (now - last_post).total_seconds() >= cooldown


def update_cooldown(npc_id: str, channel: str, now: datetime) -> None:
    """Record that NPC posted to channel."""
    if npc_id not in _npc_cooldowns:
        _npc_cooldowns[npc_id] = {}
    _npc_cooldowns[npc_id][channel] = now


async def fetch_undistributed_ambient_events(conn: asyncpg.Connection) -> List[Dict[str, Any]]:
    """Fetch ambient events that haven't expired and haven't been fully distributed."""
    rows = await conn.fetch(
        """
        SELECT ae.id, ae.sim_date, ae.type, ae.topic, ae.intensity, ae.sentiment,
               ae.confidence, ae.expires_at, ae.payload
        FROM ambient_events ae
        WHERE (ae.expires_at IS NULL OR ae.expires_at > now())
        ORDER BY ae.created_at ASC
        LIMIT 10
        """
    )
    return [dict(r) for r in rows]


async def check_already_delivered(conn: asyncpg.Connection, ambient_id: str, npc_id: str) -> bool:
    """Check if ambient event was already delivered to this NPC."""
    row = await conn.fetchrow(
        "SELECT 1 FROM ambient_deliveries WHERE ambient_event_id=$1 AND npc_id=$2",
        ambient_id, npc_id
    )
    return row is not None


async def record_delivery(conn: asyncpg.Connection, ambient_id: str, npc_id: str) -> None:
    """Record that ambient event was delivered to NPC."""
    await conn.execute(
        """INSERT INTO ambient_deliveries (ambient_event_id, npc_id)
           VALUES ($1, $2) ON CONFLICT DO NOTHING""",
        ambient_id, npc_id
    )


async def create_ambient_seen_event(
    conn: asyncpg.Connection,
    ambient_event: Dict[str, Any],
    npc_id: str,
    sim_ts: datetime,
) -> Dict[str, Any]:
    """Create AMBIENT_SEEN event for NPC in events table."""
    ambient_id = ambient_event["id"]
    event_id = f"evt_ambient_seen_{ambient_id}_{npc_id}"

    payload = {
        "ambient_event_id": ambient_id,
        "topic": ambient_event["topic"],
        "intensity": ambient_event["intensity"],
        "sentiment": ambient_event["sentiment"],
        "summary_fi": ambient_event["payload"].get("summary_fi", ""),
        "facts": ambient_event["payload"].get("facts", []),
    }

    event = {
        "id": event_id,
        "type": "AMBIENT_SEEN",
        "place_id": None,
        "actors": [npc_id],
        "targets": [],
        "publicness": 0.0,  # Internal event, not public
        "severity": ambient_event["intensity"] * 0.3,
        "ts_local": sim_ts.isoformat(),
        "payload": payload,
    }

    # Insert event (idempotent)
    await conn.execute(
        """
        INSERT INTO events (id, sim_ts, place_id, type, actors, targets, publicness, severity, payload)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9::jsonb)
        ON CONFLICT (id) DO NOTHING
        """,
        event_id,
        sim_ts,
        None,
        "AMBIENT_SEEN",
        json.dumps([npc_id]),
        json.dumps([]),
        0.0,
        event["severity"],
        json.dumps(payload),
    )

    return event


async def distribute_ambient_events(sim_ts: datetime) -> int:
    """
    Distribute ambient events to NPCs and generate reactions.
    Returns count of render jobs enqueued.
    """
    assert db_pool is not None
    assert redis_client is not None

    npcs = get_npc_profiles()
    if not npcs:
        return 0

    jobs_enqueued = 0

    async with db_pool.acquire() as conn:
        ambient_events = await fetch_undistributed_ambient_events(conn)
        if not ambient_events:
            return 0

        for ae in ambient_events:
            ambient_id = ae["id"]
            topic = ae["topic"]
            payload = ae["payload"] if isinstance(ae["payload"], dict) else json.loads(ae["payload"])
            ae["payload"] = payload  # Ensure dict

            for npc in npcs:
                npc_id = npc.id

                # Skip if already delivered
                if await check_already_delivered(conn, ambient_id, npc_id):
                    continue

                # Deterministic visibility check
                if not should_deliver_ambient(ambient_id, npc_id):
                    # Mark as "delivered" (with no action) to prevent re-processing
                    await record_delivery(conn, ambient_id, npc_id)
                    continue

                # Create AMBIENT_SEEN event
                seen_event = await create_ambient_seen_event(conn, ae, npc_id, sim_ts)

                # Get NPC profile for appraisal
                profile_row = await conn.fetchrow(
                    "SELECT profile FROM npc_profiles WHERE npc_id=$1", npc_id
                )
                npc_profile = {}
                if profile_row:
                    prof = profile_row["profile"]
                    npc_profile = json.loads(prof) if isinstance(prof, str) else prof

                # Appraise: determine intent based on topic + personality
                intent, draft = appraise_ambient(topic, npc_profile)

                # Record delivery
                await record_delivery(conn, ambient_id, npc_id)

                # Skip if NPC decides to ignore
                if intent == "IGNORE" or not draft:
                    continue

                # Map intent to channel
                channel = "FEED" if intent == "POST_FEED" else "CHAT"

                # Check cooldown
                if not check_cooldown(npc_id, channel, sim_ts):
                    continue

                # Enqueue render job
                job = {
                    "channel": channel,
                    "author_id": npc_id,
                    "source_event_id": seen_event["id"],
                    "prompt_context": {
                        "summary": f"Reaction to {topic}: {payload.get('summary_fi', '')}",
                        "event": seen_event,
                        "ambient_topic": topic,
                        "ambient_payload": payload,
                        "draft": draft,
                        "impact": ae["intensity"],
                        "sim_ts": sim_ts.isoformat(),
                    },
                }
                await redis_client.lpush(settings.render_queue, json.dumps(job))
                update_cooldown(npc_id, channel, sim_ts)
                jobs_enqueued += 1
                print(f"[engine] ambient reaction: {npc_id} -> {intent} on {topic}")

    return jobs_enqueued


def build_rich_payload(event_type: str, rng: random.Random, npcs: list) -> Dict[str, Any]:
    """Build rich payload with content for the event type."""
    payload: Dict[str, Any] = {"source": "routine_injector"}

    options = PAYLOAD_OPTIONS.get(event_type, {})

    if event_type == "LOCATION_VISIT":
        if "activities" in options:
            payload["activity"] = rng.choice(options["activities"])
        if "moods" in options:
            payload["mood"] = rng.choice(options["moods"])

    elif event_type == "SMALL_TALK":
        if "topics" in options:
            payload["topic"] = rng.choice(options["topics"])
        if "moods" in options:
            payload["mood"] = rng.choice(options["moods"])

    elif event_type == "CUSTOMER_INTERACTION":
        if "items" in options:
            payload["item"] = rng.choice(options["items"])
        if "moods" in options:
            payload["mood"] = rng.choice(options["moods"])

    return payload


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
    event_type = template["type"]

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

    # Build rich payload with content
    payload = build_rich_payload(event_type, rng, npcs)
    payload["tick"] = tick_index

    # For SMALL_TALK, sometimes add a target NPC
    targets = []
    if event_type == "SMALL_TALK" and rng.random() < 0.4:
        other_npcs = [n for n in npcs if n.id != npc.id]
        if other_npcs:
            targets = [rng.choice(other_npcs).id]

    return {
        "id": event_id,
        "type": event_type,
        "place_id": place.id,
        "actors": [npc.id],
        "targets": targets,
        "publicness": template["publicness"],
        "severity": template["severity"],
        "ts_local": sim_ts.isoformat(),
        "payload": payload,
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

    # Distribute ambient events every 30 ticks (~30 seconds)
    if tick_index > 0 and tick_index % 30 == 0:
        try:
            ambient_jobs = await distribute_ambient_events(sim_ts)
            if ambient_jobs > 0:
                print(f"[engine] distributed ambient events, enqueued {ambient_jobs} reactions")
        except Exception as e:
            # Don't crash the tick loop if ambient tables don't exist yet
            if "ambient_events" not in str(e):
                print(f"[engine] ambient distribution error: {e}")

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
        tick_index = await fetch_latest_tick_index() + 1
        # Advance RNG state to match resumed tick position
        for _ in range(tick_index // 10):
            rng.choice(ROUTINE_EVENT_TEMPLATES)
            rng.choice(get_places())
        print(
            f"[engine] sim clock start sim_ts={sim_ts.isoformat()} seed={settings.sim_seed} tick_ms={settings.sim_tick_ms} resume_tick={tick_index}"
        )
        while True:
            sim_ts = await tick_once(sim_ts, tick_index, rng, event_types)
            tick_index += 1
            await asyncio.sleep(settings.sim_tick_ms / 1000.0)
    finally:
        await close_services()
        print("[engine] stopped")


if __name__ == "__main__":
    asyncio.run(main())
