# Suomivillage / Koivulahti

A deterministic village simulation that generates social media-style content from events. NPCs live in a Finnish village, interact with each other, and their actions are rendered as FEED, CHAT, and NEWS posts using local LLMs.

## What is this?

**Koivulahti** (Birch Bay) is an event-driven simulation engine that:

- Runs a continuous simulation of a small Finnish village with ~10 NPCs
- Generates events (conversations, conflicts, visits, interactions) deterministically
- Tracks NPC relationships, memories, and goals
- Computes impact scores for events based on novelty, conflict, and social dynamics
- Generates social media-style posts (FEED/CHAT/NEWS) using local LLMs (llama.cpp)
- Maintains full determinism for reproducibility and replay

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for development)
- 4GB+ RAM for CPU inference (16GB+ recommended for GPU)
- ~4.5GB disk space for model

### 1. Download the LLM model

```bash
# From project root
cd koivulahti
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install huggingface-hub

# Download Mistral 7B Instruct (Q4 quantized)
hf download TheBloke/Mistral-7B-Instruct-v0.2-GGUF \
  mistral-7b-instruct-v0.2.Q4_K_M.gguf \
  --local-dir models
```

### 2. Start the services

```bash
cd koivulahti/infra

# Option A: CPU mode (slower, no GPU required)
docker-compose --profile cpu up -d

# Option B: GPU mode (requires NVIDIA GPU + nvidia-docker)
docker-compose --profile gpu up -d
```

### 3. Watch it run

```bash
# View engine logs (simulation events)
docker-compose logs engine -f

# View worker logs (content generation)
docker-compose logs workers -f

# Check recent events via API
curl http://localhost:8082/events?limit=5 | jq

# Check generated posts
curl http://localhost:8082/posts?limit=5 | jq
```

### 4. Run smoke tests

```bash
# From koivulahti directory
source venv/bin/activate
python tests/test_smoke.py
```

## Architecture Overview

```
┌─────────────┐
│   Engine    │  Generates events, computes impact, updates state
│  (Python)   │  → Enqueues render jobs to Redis
└──────┬──────┘
       │
       ├─→ PostgreSQL (events, state, posts)
       └─→ Redis Queue (render jobs)
              │
              ↓
       ┌──────────┐
       │ Workers  │  Pop jobs, call LLM Gateway, persist posts
       │ (Python) │
       └────┬─────┘
            │
            ↓
    ┌─────────────┐
    │LLM Gateway  │  Adapter for llama.cpp, validates JSON
    │  (FastAPI)  │
    └─────┬───────┘
          │
          ↓
   ┌──────────────┐
   │ llama.cpp    │  Mistral 7B Instruct (local inference)
   │   Server     │
   └──────────────┘
```

**Key Features:**
- **Deterministic:** Seeded RNG ensures reproducible simulations
- **Event-driven:** Truth comes from events, not LLM hallucinations
- **Impact-based:** Only high-impact events generate posts (configurable thresholds)
- **Memory & Relationships:** NPCs remember events and relationship states evolve
- **Local LLM:** Privacy-first, no external API calls

## Project Structure

```
koivulahti/
├── services/
│   ├── engine/          # Simulation loop, event injectors
│   ├── workers/         # Content generation workers
│   ├── llm_gateway/     # LLM adapter & JSON validation
│   └── api/             # Read API for events/posts
├── packages/shared/
│   ├── data/            # Catalog (event_types.json)
│   ├── db.py            # Database utilities
│   ├── schemas.py       # Pydantic models
│   └── settings.py      # Shared config
├── migrations/          # PostgreSQL schema
├── infra/
│   ├── docker-compose.yml
│   └── .env            # Configuration
├── docs/
│   ├── architecture.md # Detailed architecture + diagrams
│   ├── contracts.md    # API contracts
│   └── status-and-next.md # Current status & roadmap
├── tests/
│   └── test_smoke.py   # Integration tests
└── models/             # Downloaded LLM models (.gguf)
```

## Configuration

Key environment variables in `infra/.env`:

```bash
# Simulation settings
SIM_SEED=1234                    # Random seed for determinism
SIM_TICK_MS=1000                 # Simulation tick interval (ms)

# Impact thresholds (0.0-1.0)
IMPACT_THRESHOLD_FEED=0.6        # FEED posts threshold
IMPACT_THRESHOLD_CHAT=0.4        # CHAT posts threshold
IMPACT_THRESHOLD_NEWS=0.8        # NEWS posts threshold

# LLM settings
LLM_SERVER_URL=http://llm-server-cpu:8080
LLM_MODEL_PATH=/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf
LLM_TEMPERATURE=0.7
```

## API Endpoints

Once running, the API is available at `http://localhost:8082`:

### Events
```bash
GET /events?limit=50
```

Returns recent simulation events with impact scores.

### Posts
```bash
GET /posts?limit=50
```

Returns generated posts (FEED/CHAT/NEWS).

### Health
```bash
GET /health
```

### LLM Gateway
```bash
POST http://localhost:8081/generate
```

Direct access to content generation (see `docs/contracts.md`).

## Development

### Running tests

```bash
cd koivulahti
source venv/bin/activate
python tests/test_smoke.py
```

### Database migrations

```bash
# Migrations run automatically on first startup
# To reset: docker-compose down -v && docker-compose up -d
```

### Viewing logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs engine -f
docker-compose logs workers -f
docker-compose logs llm-gateway -f
```

### Rebuilding services

```bash
# After code changes
docker-compose build engine workers llm-gateway api
docker-compose up -d
```

## Current Status

**Working:**
- ✅ Deterministic simulation engine with continuous tick loop
- ✅ Day 1 seed events (17 scripted events from catalog)
- ✅ Post-Day 1 routine event injector (generates events every 10 ticks)
- ✅ Impact scoring system (novelty, conflict, publicness, status, cascade)
- ✅ Event effects (memories, relationship deltas)
- ✅ LLM Gateway with llama.cpp integration
- ✅ Content generation workers
- ✅ Read API for events/posts
- ✅ Smoke tests passing
- ✅ CORS middleware
- ✅ CPU/GPU profiles for llama.cpp

**In Progress:**
- 🚧 Wire prompt templates from catalog (currently hardcoded)
- 🚧 Daily NEWS digest (1x per sim day, top events)
- 🚧 Nightly memory summaries & compaction
- 🚧 Moderation & rate limits enforcement
- 🚧 World snapshots for replay

**Planned:**
- 📋 Agent decision loop (NPCs choose actions via LLM)
- 📋 Director/injectors for narrative arcs
- 📋 Admin UI
- 📋 Read-only village UI

See [docs/status-and-next.md](koivulahti/docs/status-and-next.md) for detailed roadmap.

## Documentation

- **[Architecture](koivulahti/docs/architecture.md)** - System design, data flows, diagrams
- **[Contracts](koivulahti/docs/contracts.md)** - API contracts, database schema
- **[Status & Roadmap](koivulahti/docs/status-and-next.md)** - Current progress, next milestones

## Technical Details

### How it works

1. **Engine** seeds the world (places, NPCs, relationships, goals) on first run
2. **Day 1 events** are injected from the catalog (scripted baseline narrative)
3. **Tick loop** runs continuously (default: 1 tick/second)
4. **Routine injector** generates events every 10 ticks:
   - Selects NPC deterministically (round-robin)
   - Chooses event type via seeded RNG (LOCATION_VISIT, SMALL_TALK, CUSTOMER_INTERACTION)
   - Matches place by type (sauna/beach, cafe, shop)
5. Each event is **processed**:
   - Inserted to `events` table with `sim_ts`
   - Effects applied (memories, relationship updates)
   - Impact score computed (0.0-1.0)
   - Render jobs enqueued if impact ≥ threshold
6. **Workers** pop render jobs from Redis:
   - Build prompt with event context
   - Call LLM Gateway
   - Parse JSON response
   - Persist to `posts` table
7. **Posts** are available via API

### Impact Scoring

Impact is a weighted sum (0.0-1.0) of:

- **Novelty** (30%): Inverse frequency of event type in last 24h
- **Conflict** (25%): Event severity
- **Publicness** (20%): How public the event is
- **Status** (15%): Average status of involved NPCs
- **Cascade** (10%): Potential for effects (relationship deltas, reputation)

Only events with `impact >= threshold[channel]` generate posts:
- CHAT: 0.4 (everyday conversations)
- FEED: 0.6 (notable events)
- NEWS: 0.8 (major village news)

### Determinism

- All randomness uses seeded RNG (`SIM_SEED`)
- RNG threaded through tick loop for reproducibility
- LLM output does not affect simulation truth (events)
- Events can be replayed from database (future: with snapshots)

## License

[License TBD]

## Contributing

Contributions welcome! This is an experimental project exploring deterministic social simulations with local LLMs.

**Areas to explore:**
- Better event injectors (goal-driven, narrative-driven)
- Improved impact scoring
- Memory retrieval & compaction strategies
- Multi-agent decision loops
- UI/visualization

## Contact

[Contact info TBD]
