# Koivulahti Architecture (Live)

This repo runs a deterministic village simulation that produces content from events.

## Services

- `services/engine`  
  Simulation tick + event injector. Source of truth for `events` and relationship/memory effects. Pushes render jobs to Redis when impact passes thresholds.
- `services/workers`  
  Consume Redis render jobs, build prompts, call `llm-gateway`, persist to `posts`.
- `services/llm_gateway`  
  Single adapter boundary for all LLM calls. Enforces strict JSON output and later will implement repair + caching.
- `services/api`  
  Read API for posts/events + admin stubs.
- Infra: Postgres (event store + state tables), Redis (render queue).

## Data flow

1. Engine seeds baseline world data if DB is empty:
   - Places, NPC entities and full `npc_profiles`
   - Initial relationship edges
   - Seeded goals
2. Engine injects Day 1 seed events from the catalog and inserts them into `events`.
3. For each event, engine computes impact and enqueues render jobs to Redis for the event type's `render.default_channels`.
4. Workers pop jobs, call gateway `/generate`, store results in `posts`.
5. API exposes `/posts` and `/events` for UI/admin.

## Determinism

- All simulation randomness must be seeded via env `SIM_SEED` and logged in events.
- LLM output must not affect truth events; only actions/text derived from events.
- Replay should be possible from `events` + `world_snapshots`.

## Canonical contracts

Primary runtime source: `packages/shared/data/event_types.json`.  
It contains:
- moderation rules + rate limits
- places
- npc profiles + goals + triggers
- relationship initialization
- event types catalog (payload schemas, effects, default render channels)
- prompt templates and Day 1 seed events

Archived specs are in `docs/archive/` for reference only.

