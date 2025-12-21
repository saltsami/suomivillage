"""Decision Service main loop - processes decision jobs from Redis."""

import asyncio
import json
import os
from typing import Any, Dict, Optional

import asyncpg
from redis.asyncio import Redis

from .context import build_decision_context
from .decision import make_decision, log_decision, decision_to_render_job
from .prompts import build_decision_prompt


# Environment config
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://koivulahti:koivulahti@postgres:5432/koivulahti")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DECISION_QUEUE = os.getenv("DECISION_QUEUE", "decision_jobs")
RENDER_QUEUE = os.getenv("RENDER_QUEUE", "render_jobs")

# Rate limiting - minimum seconds between Gemini calls (default 10s = 6 calls/min)
MIN_CALL_INTERVAL = float(os.getenv("DECISION_MIN_INTERVAL", "10.0"))

# Track last call time for rate limiting
_last_call_time: float = 0.0

# Global connections
redis_client: Optional[Redis] = None
db_pool: Optional[asyncpg.Pool] = None


async def init_services() -> None:
    """Initialize Redis and database connections."""
    global redis_client, db_pool

    print("[decision] connecting to Redis...")
    redis_client = Redis.from_url(REDIS_URL, decode_responses=True)

    print("[decision] connecting to PostgreSQL...")
    db_pool = await asyncpg.create_pool(DATABASE_URL)

    print("[decision] services initialized")


async def close_services() -> None:
    """Close connections."""
    global redis_client, db_pool

    if redis_client:
        await redis_client.close()
    if db_pool:
        await db_pool.close()

    print("[decision] services closed")


async def fetch_job() -> Dict[str, Any]:
    """Fetch next decision job from Redis (blocking)."""
    assert redis_client is not None
    _, job_json = await redis_client.brpop(DECISION_QUEUE)
    return json.loads(job_json)


async def enqueue_render_job(job: Dict[str, Any]) -> None:
    """Push render job to Redis."""
    assert redis_client is not None
    await redis_client.lpush(RENDER_QUEUE, json.dumps(job))


async def process_job(job: Dict[str, Any]) -> None:
    """Process a single decision job."""
    global _last_call_time
    assert db_pool is not None

    job_id = job.get("job_id", "unknown")
    npc_id = job.get("npc_id", "")
    stimulus = job.get("stimulus", {})

    print(f"[decision] processing: job={job_id}, npc={npc_id}, type={stimulus.get('event_type')}")

    if not npc_id:
        print(f"[decision] ERROR: missing npc_id in job {job_id}")
        return

    # Rate limiting - wait if needed
    import time
    now = time.time()
    elapsed = now - _last_call_time
    if elapsed < MIN_CALL_INTERVAL:
        wait_time = MIN_CALL_INTERVAL - elapsed
        print(f"[decision] rate limit: waiting {wait_time:.1f}s")
        await asyncio.sleep(wait_time)
    _last_call_time = time.time()

    async with db_pool.acquire() as conn:
        # Build context
        context = await build_decision_context(conn, npc_id, stimulus)

        if not context:
            print(f"[decision] ERROR: NPC not found: {npc_id}")
            return

        # Make decision
        decision = await make_decision(context)

        action = decision.get("action", "IGNORE")
        latency = decision.get("latency_ms", 0)
        print(f"[decision] result: npc={npc_id}, action={action}, intent={decision.get('intent')}, latency={latency}ms")

        # Log decision
        prompt = build_decision_prompt(context)
        await log_decision(
            conn=conn,
            job_id=job_id,
            npc_id=npc_id,
            stimulus_event_id=stimulus.get("event_id"),
            stimulus_type=stimulus.get("event_type", "UNKNOWN"),
            context=context,
            llm_input=prompt,
            decision=decision,
        )

        # If action requires rendering, enqueue render job
        render_job = decision_to_render_job(job_id, npc_id, stimulus, decision)

        if render_job:
            await enqueue_render_job(render_job)
            print(f"[decision] enqueued render: {render_job['job_id']} -> {render_job['channel']}")
        else:
            print(f"[decision] no render needed (action={action})")


async def main() -> None:
    """Main loop."""
    await init_services()
    print("[decision] started, waiting for jobs...")

    try:
        while True:
            try:
                job = await fetch_job()
                await process_job(job)
            except Exception as e:
                print(f"[decision] ERROR processing job: {e}")
                import traceback
                traceback.print_exc()
                # Small delay before retrying
                await asyncio.sleep(1)

    except asyncio.CancelledError:
        print("[decision] shutting down...")
    finally:
        await close_services()
        print("[decision] stopped")


if __name__ == "__main__":
    asyncio.run(main())
