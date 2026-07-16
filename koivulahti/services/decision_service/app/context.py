"""Context Builder - fetches NPC context from database for decision-making."""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import asyncpg


async def fetch_npc_profile(conn: asyncpg.Connection, npc_id: str) -> Optional[Dict[str, Any]]:
    """Fetch NPC profile from database."""
    row = await conn.fetchrow(
        "SELECT profile FROM npc_profiles WHERE npc_id = $1",
        npc_id
    )
    if not row:
        return None

    profile = row["profile"]
    if isinstance(profile, str):
        profile = json.loads(profile)
    return profile


async def fetch_recent_memories(
    conn: asyncpg.Connection,
    npc_id: str,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """Fetch recent memories (last 24h)."""
    rows = await conn.fetch(
        """
        SELECT m.event_id, m.summary, m.importance, m.created_at, e.type as event_type
        FROM memories m
        LEFT JOIN events e ON m.event_id = e.id
        WHERE m.npc_id = $1 AND m.created_at > now() - interval '24 hours'
        ORDER BY m.created_at DESC
        LIMIT $2
        """,
        npc_id, limit
    )
    return [
        {
            "event_id": row["event_id"],
            "summary": row["summary"],
            "importance": float(row["importance"]) if row["importance"] else 0.1,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "event_type": row["event_type"],
        }
        for row in rows
    ]


async def fetch_important_memories(
    conn: asyncpg.Connection,
    npc_id: str,
    min_importance: float = 0.5,
    limit: int = 3
) -> List[Dict[str, Any]]:
    """Fetch high-importance memories."""
    rows = await conn.fetch(
        """
        SELECT m.event_id, m.summary, m.importance, m.created_at, e.type as event_type
        FROM memories m
        LEFT JOIN events e ON m.event_id = e.id
        WHERE m.npc_id = $1 AND m.importance >= $2
        ORDER BY m.importance DESC
        LIMIT $3
        """,
        npc_id, min_importance, limit
    )
    return [
        {
            "event_id": row["event_id"],
            "summary": row["summary"],
            "importance": float(row["importance"]) if row["importance"] else 0.1,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "event_type": row["event_type"],
        }
        for row in rows
    ]


async def fetch_related_memories(
    conn: asyncpg.Connection,
    npc_id: str,
    involved_actors: List[str],
    limit: int = 3
) -> List[Dict[str, Any]]:
    """Fetch memories involving the same actors."""
    if not involved_actors:
        return []

    # Build JSONB contains query for actors
    actors_json = json.dumps(involved_actors)

    rows = await conn.fetch(
        """
        SELECT m.event_id, m.summary, m.importance, m.created_at, e.type as event_type
        FROM memories m
        JOIN events e ON m.event_id = e.id
        WHERE m.npc_id = $1
          AND (e.actors @> $2::jsonb OR e.targets @> $2::jsonb)
        ORDER BY m.created_at DESC
        LIMIT $3
        """,
        npc_id, actors_json, limit
    )
    return [
        {
            "event_id": row["event_id"],
            "summary": row["summary"],
            "importance": float(row["importance"]) if row["importance"] else 0.1,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "event_type": row["event_type"],
        }
        for row in rows
    ]


async def fetch_relationships(
    conn: asyncpg.Connection,
    npc_id: str,
    involved_actors: List[str]
) -> Dict[str, Dict[str, Any]]:
    """Fetch relationships with involved actors."""
    if not involved_actors:
        return {}

    # Filter out self
    other_actors = [a for a in involved_actors if a != npc_id]
    if not other_actors:
        return {}

    rows = await conn.fetch(
        """
        SELECT r.to_npc, r.trust, r.respect, r.affection, r.jealousy, r.fear, r.grievances,
               e.name
        FROM relationships r
        LEFT JOIN entities e ON r.to_npc = e.id
        WHERE r.from_npc = $1 AND r.to_npc = ANY($2)
        """,
        npc_id, other_actors
    )

    result = {}
    for row in rows:
        grievances = row["grievances"]
        if isinstance(grievances, str):
            try:
                grievances = json.loads(grievances)
            except json.JSONDecodeError:
                grievances = []

        result[row["to_npc"]] = {
            "npc_id": row["to_npc"],
            "name": row["name"] or row["to_npc"].replace("npc_", "").capitalize(),
            "trust": row["trust"] or 0,
            "respect": row["respect"] or 0,
            "affection": row["affection"] or 0,
            "jealousy": row["jealousy"] or 0,
            "fear": row["fear"] or 0,
            "grievances": grievances if isinstance(grievances, list) else [],
        }

    return result


async def fetch_active_goals(
    conn: asyncpg.Connection,
    npc_id: str,
    limit: int = 3
) -> List[Dict[str, Any]]:
    """Fetch active goals for NPC."""
    rows = await conn.fetch(
        """
        SELECT horizon, priority, goal_json
        FROM goals
        WHERE npc_id = $1 AND status = 'active'
        ORDER BY priority DESC
        LIMIT $2
        """,
        npc_id, limit
    )

    goals = []
    for row in rows:
        goal_json = row["goal_json"]
        if isinstance(goal_json, str):
            try:
                goal_json = json.loads(goal_json)
            except json.JSONDecodeError:
                goal_json = {}

        goals.append({
            "goal_type": goal_json.get("type", "unknown"),
            "description": goal_json.get("target", goal_json.get("metric", "")),
            "priority": float(row["priority"]) if row["priority"] else 0.5,
            "horizon": row["horizon"] or "short",
        })

    return goals


async def build_decision_context(
    conn: asyncpg.Connection,
    npc_id: str,
    stimulus: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Build full decision context for an NPC.

    Args:
        conn: Database connection
        npc_id: The NPC making the decision
        stimulus: The event/trigger to react to

    Returns:
        Full context dict or None if NPC not found
    """
    # Fetch profile
    profile = await fetch_npc_profile(conn, npc_id)
    if not profile:
        return None

    # Extract involved actors from stimulus
    involved_actors = []
    if stimulus.get("actors"):
        involved_actors.extend(stimulus["actors"])
    if stimulus.get("targets"):
        involved_actors.extend(stimulus["targets"])
    if stimulus.get("original_author"):
        involved_actors.append(stimulus["original_author"])

    # Remove duplicates and self
    involved_actors = list(set(a for a in involved_actors if a and a != npc_id))

    # Fetch memories in parallel (conceptually - Python asyncio)
    recent_memories = await fetch_recent_memories(conn, npc_id)
    important_memories = await fetch_important_memories(conn, npc_id)
    related_memories = await fetch_related_memories(conn, npc_id, involved_actors)

    # Fetch relationships
    relationships = await fetch_relationships(conn, npc_id, involved_actors)

    # Fetch goals
    active_goals = await fetch_active_goals(conn, npc_id)

    # Build context
    context = {
        # Identity
        "npc_id": npc_id,
        "name": profile.get("name", npc_id.replace("npc_", "").capitalize()),
        "role": profile.get("role", "villager"),
        "archetypes": profile.get("archetypes", []),
        "bio": profile.get("bio", ""),
        "traits": profile.get("traits", {}),
        "values": profile.get("values", {}),
        "voice": profile.get("voice", {}),

        # Memories
        "recent_memories": recent_memories,
        "important_memories": important_memories,
        "related_memories": related_memories,

        # Relationships
        "relationships": relationships,

        # Goals
        "active_goals": active_goals,

        # Stimulus
        "stimulus": stimulus,
    }

    return context
