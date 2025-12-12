from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg

from .settings import Settings


async def create_pool(settings: Settings) -> asyncpg.Pool:
    return await asyncpg.create_pool(settings.database_url)


@asynccontextmanager
async def get_connection(pool: asyncpg.Pool) -> AsyncIterator[asyncpg.Connection]:
    conn = await pool.acquire()
    try:
        yield conn
    finally:
        await pool.release(conn)
