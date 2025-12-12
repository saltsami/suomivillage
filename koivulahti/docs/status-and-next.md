# Current Status & Next Steps (Live)

Updated: 2025-12-12

## What’s implemented now

- Repo scaffold per `repo_structure.txt`.
- Infra
  - `infra/docker-compose.yml` builds all services from repo root, with CPU/GPU llama.cpp profiles.
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
2. Start one profile:
   - GPU: `docker compose --env-file .env --profile gpu up --build`
   - CPU: `docker compose --env-file .env --profile cpu up --build`
   (set `LLM_SERVER_URL` in `.env` to `http://llm-server-gpu:8080` or `http://llm-server-cpu:8080`).
3. Verify:
   - `http://localhost:8081/health`
   - `http://localhost:8082/docs`
   - `GET /events` and `/posts`

## Known gaps / TODO

Engine
- Deterministic sim clock + tick scheduler beyond Day 1.
- Proper impact scoring (novelty/conflict/status/cascade) per catalog.
- Apply event `effects` to relationships/memory/reputation.
- Daily NEWS digest event (1x sim day) + enqueue NEWS job.
- Nightly memory summaries per NPC + memory compaction.
- World snapshots + replay.

Agents
- Decision loop producing `action_schema` JSON using LLM.
- Rule validation at engine boundary.
- Director/injectors after Day 1.

Content
- Feed/chat/news prompt templates from catalog wired in (not just summary).
- Moderation + rate limits enforced in gateway/workers before persisting.
- FEED + CHAT rendering from the same event when both channels are triggered.

LLM gateway
- Real llama.cpp adapter using `LLM_SERVER_URL`.
- Strict schema validation + JSON repair + caching (single adapter boundary).

API/Admin/UI
- Admin endpoints that control run/seed/replay.
- Read-only UI (later milestone).

## Next milestone (Demo‑ready) roadmap

Goal: “live Day 1 → continuous sim” demo with believable FEED/CHAT/NEWS.

1. Wire prompt templates
   - Load `feed_prompt`, `chat_prompt`, `news_prompt` from catalog.
   - Workers/gateway build prompts consistently per channel.
2. Implement real LLM gateway
   - Add llama.cpp adapter + schema validation/repair + caching.
   - Keep all backend quirks inside gateway.
3. Enforce moderation + rate limits
   - Apply `moderation_rules` and `rate_limits` from catalog before insert.
4. Extend engine past Day 1
   - Deterministic sim clock + seeded tick loop.
   - Generate next events/actions via scheduler/injectors.
5. Daily NEWS digest
   - Once per sim day, pick top events by impact and publish a NEWS_PUBLISHED event.
6. Nightly memory summary
   - Per NPC, write 1 summary memory per sim day; compact older episodic memories.
7. Replay baseline
   - Persist `world_snapshots` at day boundaries and add replay script/endpoint.

## Milestone after demo (Agent Decision MVP)

1. NPC perception/retrieval loop (event‑triggered + scheduled windows).
2. LLM outputs **action JSON only** per `action_schema`.
3. Engine validates rules, emits resulting events, and updates state deterministically.

1. Wire catalog prompt templates into workers/gateway.
2. Implement gateway llama.cpp adapter + schema validation/repair.
3. Expand engine to:
   - maintain sim_ts and tick
   - choose next events/actions deterministically
   - apply relationship deltas and write memories.
