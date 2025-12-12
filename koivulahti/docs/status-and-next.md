# Current Status & Next Steps (Live)

Updated: 2025-12-12

## What’s implemented now

- Repo scaffold per `repo_structure.txt`.
- Infra
  - `infra/docker-compose.yml` builds all services from repo root.
  - `infra/.env.example` includes required env vars.
- Shared packages
  - `packages/shared/settings.py`, `db.py`, `schemas.py`
  - `packages/shared/data_loader.py` loads the canonical catalog.
  - `packages/shared/data/event_types.json` and `kick_off_pack.json` are in-tree.
- Migrations
  - `001_init.sql` (events/posts/jobs)
  - `002_kickoff_tables.sql` (entities/profiles/relationships/memories/goals)
- Engine (`services/engine/app/runner.py`)
  - Seeds DB from catalog if empty (places, NPCs, profiles, relationship edges, goals).
  - Injects Day 1 events into `events` if no events exist.
  - Enqueues render jobs to Redis based on event-type default channels and impact thresholds.
- Workers (`services/workers/app/worker.py`)
  - Pops Redis jobs, fetches author profile, builds prompt from event context.
  - Calls gateway and persists returned post to `posts`.
- LLM gateway (`services/llm_gateway/app/main.py`)
  - Stub `/generate` that returns deterministic JSON.
- API (`services/api/app/main.py`)
  - `/health`, `/posts`, `/events` read endpoints.
  - admin endpoints stubbed.

## How to run

From `infra/`:
1. `cp .env.example .env` and edit values.
2. `docker compose --env-file .env --profile gpu up --build`
3. Verify:
   - `http://localhost:8081/health`
   - `http://localhost:8082/docs`
   - `GET /events` and `/posts`

## Known gaps / TODO

Engine
- Deterministic sim clock + tick scheduler beyond Day 1.
- Apply event `effects` to relationships/memory/reputation.
- World snapshots + replay.
- Proper impact scoring (novelty/conflict/status/cascade).

Agents
- Decision loop producing `action_schema` JSON using LLM.
- Rule validation at engine boundary.
- Director/injectors after Day 1.

Content
- Moderation + rate limits enforced in gateway/workers.
- Feed/chat/news prompt templates from catalog wired in.

LLM gateway
- Real llama.cpp adapter.
- Strict schema validation + JSON repair + caching.

API/Admin/UI
- Admin endpoints that control run/seed/replay.
- Read-only UI (later milestone).

## Suggested next session plan

1. Wire catalog prompt templates into workers/gateway.
2. Implement gateway llama.cpp adapter + schema validation/repair.
3. Expand engine to:
   - maintain sim_ts and tick
   - choose next events/actions deterministically
   - apply relationship deltas and write memories.

