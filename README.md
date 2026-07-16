# Suomivillage / Koivulahti

Koivulahti is an event-driven Finnish village simulation prototype. It stores world events, derives NPC memories and relationships, and renders selected events into `FEED`, `CHAT`, and `NEWS` posts.

> **Project status:** recovery and product-validation phase. The repository is useful, but the current runtime is not yet an autonomous village or a validated consumer product. The next target is a bounded seven-day Finnish live-soap pilot with six characters.

Read the full [repository and product audit](docs/REPO_AUDIT_2026-07-16.md) before extending the old roadmap. The completed infrastructure work is tracked in the [Phase 0 rescue note](docs/PHASE_0_RESCUE_2026-07-16.md).

## Current decision

- Keep the event-first architecture and content catalog.
- Do not build a generic AI-village platform.
- Keep external decision and ambient-data services opt-in.
- Build a small causal vertical slice, then validate it with real viewers.

## Safe quick start

Requirements:

- Docker with Compose v2
- Approximately 2 GB free memory for the fake-provider stack
- [`uv`](https://docs.astral.sh/uv/) only when running tests

Start the reproducible stack without an external model or API key:

```bash
cd koivulahti
./dev.sh up
```

The API is then available only on the local loopback interface:

```text
http://127.0.0.1:8082/docs
http://127.0.0.1:8082/health
http://127.0.0.1:8082/events?limit=20
http://127.0.0.1:8082/posts?limit=20
```

The default `fake` renderer is deterministic and intended for development and CI. PostgreSQL, Redis, the LLM gateway, and llama.cpp are not published to the host by the base Compose file.

Stop without deleting data:

```bash
./dev.sh down
```

## Developer commands

```bash
./dev.sh up-dev       # Loopback DB, Redis and gateway ports for diagnostics
./dev.sh config       # Validate all Compose profiles
./dev.sh build        # Build all six application images
./dev.sh test-unit    # Offline tests
./dev.sh test-e2e     # Disposable fake-provider stack and integration tests
./dev.sh logs         # Follow core application logs
./dev.sh ps           # Service status
```

`./dev.sh test-e2e` uses a separate Compose project and deletes only its own disposable volume after the run.

## Real model profiles

Local llama.cpp inference remains optional. Put a GGUF model under `koivulahti/models/`, then run:

```bash
./dev.sh up-cpu
# or, with NVIDIA Container Toolkit installed:
./dev.sh up-gpu
```

Override model settings in a private ignored file:

```bash
cp infra/.env.example infra/.env
# edit infra/.env
ENV_FILE=infra/.env ./dev.sh up-cpu
```

The cloud Decision Service is disabled by default. It currently supports the configured Gemini model through the `GEMINI_MODEL` variable, whose safe default is `gemini-3.1-flash-lite`.

```bash
# GEMINI_API_KEY must be present in the ignored infra/.env file
ENV_FILE=infra/.env ./dev.sh up-decision
```

Do not commit `.env`, API keys, or GGUF model files.

## Runtime shape

```text
Engine ──events──> PostgreSQL
  │                    │
  └──render jobs──> Redis ──> Workers ──> LLM Gateway ──> Posts
                                         │
                                         ├── fake provider (default)
                                         └── llama.cpp (opt-in)

API ──read-only views──> PostgreSQL
```

Optional, currently experimental paths:

```text
Ambient Worker ──> ambient events
Gemini Decision Service ──> IGNORE / POST_FEED / POST_CHAT / REPLY
```

The existing Decision Service chooses publishing actions, not world-changing actions. `MOVE`, `HELP`, `BORROW`, `RETURN`, and other legal world actions belong to the next vertical slice.

## Services

- `postgres`: event store and simulation state
- `migration-runner`: checksummed, ordered SQL migrations
- `redis`: current render and decision queues
- `engine`: simulation ticks, seed scenario, routine events and effects
- `workers`: render-job processing and post persistence
- `llm-gateway`: provider boundary and response normalization
- `api`: read API plus explicitly unfinished admin endpoints
- `decision-service`: opt-in Gemini publishing decision prototype
- `ambient-worker`: opt-in external stimulus prototype

## Migrations

The stack no longer relies on PostgreSQL's first-boot-only init directory. `migration-runner` applies files matching `migrations/NNN_name.sql`, records SHA-256 checksums in `schema_migrations`, and refuses changed migrations that were already applied.

Create a new migration instead of editing an applied one.

## Tests and CI

Install the locked development environment:

```bash
cd koivulahti
uv sync --locked
```

Run checks locally:

```bash
uv run ruff check packages services tests tools
uv run pytest -m "not integration"
uv run bandit -q -lll -r packages services
uv run pip-audit
./dev.sh test-e2e
```

GitHub Actions runs linting, offline tests, dependency and static-security checks, secret scanning, all application builds, and the fake-provider E2E flow.

## Repository map

```text
.
├── docs/                         # Audit and product decision
├── koivulahti/
│   ├── infra/                    # Compose and environment templates
│   ├── migrations/               # Ordered SQL migrations and runner
│   ├── packages/shared/          # Contracts, settings and provider adapters
│   ├── services/                 # API, engine, workers and optional services
│   ├── tests/                    # Offline and integration tests
│   ├── dev.sh                    # Canonical local command surface
│   ├── pyproject.toml
│   ├── uv.lock                     # Full development lock
│   └── requirements.lock           # Hash-locked container runtime export
└── .github/workflows/ci.yml
```

## Product roadmap

1. **Repository rescue:** secure startup, supported providers, CI, versioned migrations.
2. **World-action vertical slice:** six characters and a deterministic legal-action loop.
3. **Finnish content evaluation:** one renderer, daily recap and human-rated quality gates.
4. **Viewer slice:** mobile feed, chat, news, character context and one daily vote.
5. **Seven-day closed season:** continuation only if retention and story-comprehension gates pass.

The detailed gates, commercial assessment, competitor review and stop criteria are in [the audit](docs/REPO_AUDIT_2026-07-16.md).

## Security notes

- Base Compose publishes only the API, bound to `127.0.0.1` by default.
- The development override publishes diagnostics only on loopback.
- Gemini credentials are sent in the `x-goog-api-key` header, not in request URLs.
- The old feature-branch credential must still be revoked and its remote history purged separately.
- This prototype is not ready for direct public deployment.
