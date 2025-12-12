# Data & Contracts (Live)

## Postgres schema

Base event/content tables:
- `migrations/001_init.sql`
  - `events`: append-only truth
  - `world_snapshots`: full world JSON snapshots (future replay)
  - `render_jobs`: optional persistent job tracking
  - `posts`: published FEED/CHAT/NEWS items

Kickoff/world tables:
- `migrations/002_kickoff_tables.sql`
  - `entities` (`npc|place|item`)
  - `npc_profiles` (full persona JSON)
  - `relationships` (trust/respect/affection/jealousy/fear + grievances/debts)
  - `memories` (episodic memory per NPC)
  - `goals` (short/long horizon goals)

## Shared runtime models

Located in `packages/shared/schemas.py`:
- `Event`, `RenderJob`, `Post`
- `Place`, `NPCProfile`, `RelationshipEdge`, `EventTypeItem`

The JSON catalog may contain extra fields; models allow `extra` where needed.

## Redis queues

- Render queue name comes from env `RENDER_QUEUE` (default `render_jobs`).
- Queue items are JSON dictionaries like:
  - `channel`: `FEED|CHAT|NEWS`
  - `author_id`
  - `source_event_id`
  - `prompt_context`: includes `event` and `impact`

## LLM gateway contract

Endpoint: `POST /generate`

Request (`GenerateRequest` in `services/llm_gateway/app/main.py`):
- `prompt`: full prompt string
- `channel`, `author_id`, `source_event_id`
- `context`: dict with `event`, `impact`, `author_profile` (optional)
- `temperature` (optional)

Response (`GenerateResponse`):
- `channel`, `author_id`, `source_event_id`
- `tone`, `text`
- `tags[]`, `safety_notes?`

Gateway is the only place that should adapt to llama.cpp/vLLM/OpenAI endpoints.

