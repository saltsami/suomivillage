from typing import List

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Query

from packages.shared.db import create_pool, get_connection
from packages.shared.schemas import Event, Post
from packages.shared.settings import Settings

settings = Settings()
app = FastAPI(title="Koivulahti API", version="0.1.0")
pool: asyncpg.Pool | None = None


@app.on_event("startup")
async def on_startup() -> None:
    global pool
    pool = await create_pool(settings)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if pool:
        await pool.close()


async def require_pool() -> asyncpg.Pool:
    if not pool:
        raise HTTPException(status_code=503, detail="Database pool not ready")
    return pool


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.env}


@app.get("/posts", response_model=List[Post])
async def list_posts(
    limit: int = Query(50, ge=1, le=200),
    pool_dep: asyncpg.Pool = Depends(require_pool),
) -> List[Post]:
    async with get_connection(pool_dep) as conn:
        rows = await conn.fetch(
            """
            SELECT id, created_at, channel, author_id, source_event_id, tone, text, tags, safety_notes
            FROM posts
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [Post(**dict(row)) for row in rows]


@app.get("/events", response_model=List[Event])
async def list_events(
    limit: int = Query(200, ge=1, le=500),
    pool_dep: asyncpg.Pool = Depends(require_pool),
) -> List[Event]:
    async with get_connection(pool_dep) as conn:
        rows = await conn.fetch(
            """
            SELECT id, ts, sim_ts, place_id, type, actors, targets, publicness, severity, payload
            FROM events
            ORDER BY sim_ts DESC
            LIMIT $1
            """,
            limit,
        )
    return [Event(**dict(row)) for row in rows]


@app.post("/admin/run/start")
async def start_run() -> dict[str, str]:
    return {"status": "accepted", "message": "Engine start requested"}


@app.post("/admin/run/stop")
async def stop_run() -> dict[str, str]:
    return {"status": "accepted", "message": "Engine stop requested"}


@app.get("/admin/run/status")
async def run_status() -> dict[str, str]:
    return {"status": "ok", "message": "Engine status not yet implemented"}


@app.post("/admin/replay")
async def replay() -> dict[str, str]:
    return {"status": "accepted", "message": "Replay request queued"}
