# Copilot / AI Agent Instructions for Koivulahti (suomivillage)

Purpose: give AI coding agents the minimal, actionable context to be productive in this repo.

- **Big Picture**: This repo runs a simulated agent village. Key runtime components (see `docker-compose.yml`) are:
  - `engine` — simulation tick producer (creates `events` -> pushes render jobs).
  - `workers` — consume Redis jobs, build prompts, call `llm-gateway`, save `posts`.
  - `llm-gateway` — central adapter and validator for LLMs (single place to adapt endpoints/repair JSON).
  - `llm-server` — llama.cpp (GPU) server image; models are mounted into `/models`.
  - `api` — reads `posts` and `events`, exposes admin endpoints.
  - `postgres` + `redis` — persistence and queue.

- **Start / Debug (explicit commands)**: follow `readme.txt` TL;DR. Common commands:
  - Copy env: `cp infra/.env.example infra/.env`
  - With GPU: `docker compose --env-file infra/.env --profile gpu up --build`
  - Without GPU: `docker compose --env-file infra/.env up --build`
  - Useful logs: `docker compose logs -f engine`, `docker compose logs -f workers`, `docker compose logs -f llm-gateway`

- **Where to look for canonical contracts and schema**:
  - DB schema / migrations: `migrations/001_init.sql` (tables: `events`, `render_jobs`, `posts`).
  - Simulation & NPC data: `event_types.json` (channels, moderation rules, NPC profiles, action schema).
  - Shared schemas are referenced in README as `packages/shared/schemas.py` — prefer the repo's declared schema files when present.

- **Typical data flow & quick examples**:
  - Engine creates an `events` row -> calculates `impact` -> pushes `render_jobs` to Redis queue.
  - Worker pops `render_jobs`, constructs prompt (event + persona), calls `llm-gateway` `/generate`, receives JSON, writes `posts`.
  - Example API read: `GET /posts?channel=FEED&limit=50` (see `readme.txt` endpoints).

- **Project-specific conventions**:
  - Determinism matters: simulation seeds (env `SIM_SEED`) are used to reproduce runs.
  - Contracts-first: JSON schemas are source-of-truth (see README reference to `packages/shared/schemas.py`). Validate at adapter boundaries (especially `llm-gateway`).
  - Single LLM adapter pattern: all differences between backends belong in `llm-gateway` (do not scatter adapter logic across workers).

- **LLM / Prompting specifics**:
  - Gateway must return strict JSON. If model returns broken JSON, use the gateway’s repair step (a second prompt) rather than changing workers.
  - Model path must be available inside containers: set `LLM_MODEL_PATH` to a path under `/models` and place model in `models/` on host.

- **Troubleshooting notes gleaned from repo**:
  - If gateway says "did not return valid JSON": tighten prompt, reduce temperature, or use the gateway repair step.
  - If posts don't appear: inspect Redis queue, worker logs, and impact thresholds (`IMPACT_THRESHOLD_*` envs in `docker-compose.yml`).
  - GPU visibility: verify `docker run --rm --gpus all nvidia/cuda:... nvidia-smi` and use `--profile gpu`.

- **Key files to reference when coding or changing behavior**:
  - `readme.txt` — operational quickstarts and health endpoints.
  - `docker-compose.yml` — service topology, volumes, ports, and important env names.
  - `migrations/001_init.sql` — canonical DB layout and column expectations.
  - `event_types.json` — moderation rules, channels, NPC profiles, action schema.

- **When modifying LLM interactions**:
  - Update `llm-gateway` only. Keep prompt repair and schema validation inside the gateway.
  - Add tests or live-checks that assert the gateway returns valid JSON for sample prompts.

- **What NOT to change without coordination**:
  - DB migration primary keys / column names in `migrations/001_init.sql` (many services depend on these fields).
  - Redis queue names and `RENDER_QUEUE` env name — workers and engine must match.

If any section is unclear or you want more examples (prompts, test snippets, or exact file references), tell me which area to expand.
