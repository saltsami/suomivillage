# Koivulahti Architecture (Live)

This repo runs a deterministic village simulation that produces content from events.

## System Architecture

```mermaid
graph TB
    subgraph "Data Layer"
        PG[(PostgreSQL<br/>Events, State, Posts)]
        RD[(Redis<br/>Render Queue)]
        GGUF[/Model File<br/>mistral-7b.gguf/]
    end

    subgraph "Core Services"
        ENG[Engine Service<br/>Simulation Loop]
        WORK[Workers Service<br/>Content Generation]
        GATE[LLM Gateway<br/>Model Adapter]
        API[API Service<br/>Read Endpoints]
    end

    subgraph "Infrastructure"
        LLM[LLM Server<br/>llama.cpp]
        CATALOG[/Catalog Data<br/>event_types.json/]
    end

    subgraph "Clients"
        UI[UI/Admin<br/>Future]
        TEST[Tests & Scripts]
    end

    CATALOG -.->|Load| ENG
    CATALOG -.->|Load| WORK

    ENG -->|Write Events| PG
    ENG -->|Update State| PG
    ENG -->|Enqueue Jobs| RD

    WORK -->|Pop Jobs| RD
    WORK -->|Call /generate| GATE
    WORK -->|Write Posts| PG

    GATE -->|HTTP API| LLM
    LLM -.->|Load| GGUF

    API -->|Read| PG

    UI -->|HTTP| API
    TEST -->|HTTP| API
    TEST -->|HTTP| GATE

    style ENG fill:#e1f5ff
    style WORK fill:#fff4e1
    style GATE fill:#f0e1ff
    style API fill:#e1ffe1
    style PG fill:#ffe1e1
    style RD fill:#ffe1e1
```

## Services

- **`services/engine`**
  Simulation tick + event injector. Source of truth for `events` and relationship/memory effects. Pushes render jobs to Redis when impact passes thresholds.

- **`services/workers`**
  Consume Redis render jobs, build prompts, call `llm-gateway`, persist to `posts`.

- **`services/llm_gateway`**
  Single adapter boundary for all LLM calls. Enforces strict JSON output and later will implement repair + caching.

- **`services/api`**
  Read API for posts/events + admin stubs.

- **Infrastructure:** Postgres (event store + state tables), Redis (render queue), llama.cpp (LLM server).

## Event Processing Flow

```mermaid
sequenceDiagram
    participant ENG as Engine
    participant PG as PostgreSQL
    participant RD as Redis Queue
    participant WRK as Workers
    participant GATE as LLM Gateway
    participant LLM as llama.cpp

    Note over ENG: Tick N occurs
    ENG->>ENG: Generate routine event
    ENG->>PG: INSERT INTO events
    ENG->>PG: Compute impact score
    ENG->>PG: Apply effects<br/>(memories, relationships)

    alt Impact >= Threshold
        ENG->>RD: LPUSH render_job<br/>{channel, author, event}
    end

    Note over WRK: Background worker loop
    WRK->>RD: RPOP render_job
    WRK->>WRK: Build prompt from<br/>catalog template
    WRK->>GATE: POST /generate<br/>{prompt, channel, context}
    GATE->>LLM: POST /v1/chat/completions
    LLM-->>GATE: {choices: [...]}
    GATE->>GATE: Extract & validate JSON
    GATE-->>WRK: {tone, text, tags}
    WRK->>PG: INSERT INTO posts

    Note over WRK: Post available via API
```

## Simulation Tick Flow

```mermaid
flowchart TD
    START([Engine Startup]) --> SEED{DB Empty?}
    SEED -->|Yes| SEED_DATA[Seed Places, NPCs,<br/>Relationships, Goals]
    SEED -->|No| LOAD_LATEST
    SEED_DATA --> INJECT_D1[Inject Day 1<br/>Seed Events]
    INJECT_D1 --> LOAD_LATEST[Load Latest sim_ts]

    LOAD_LATEST --> INIT_LOOP[Initialize Tick Loop<br/>tick_index=0, RNG=seeded]

    INIT_LOOP --> TICK_START[Tick Start]

    TICK_START --> CHECK_ROUTINE{tick_index > 0<br/>AND tick % 10 == 0?}

    CHECK_ROUTINE -->|Yes| GEN_ROUTINE[Generate Routine Event<br/>- Select NPC round-robin<br/>- Choose template via RNG<br/>- Match place by type]
    CHECK_ROUTINE -->|No| LOG_TICK

    GEN_ROUTINE --> PROCESS[Process Event:<br/>1. Insert to DB<br/>2. Apply effects<br/>3. Compute impact<br/>4. Enqueue render jobs]

    PROCESS --> LOG_TICK{tick % 60 == 0?}

    LOG_TICK -->|Yes| PRINT[Print tick status]
    LOG_TICK -->|No| ADVANCE
    PRINT --> ADVANCE[sim_ts += SIM_TICK_MS]

    ADVANCE --> SLEEP[Sleep SIM_TICK_MS ms]
    SLEEP --> INC[tick_index += 1]
    INC --> TICK_START

    style START fill:#e1f5ff
    style GEN_ROUTINE fill:#fff4e1
    style PROCESS fill:#ffe1e1
    style ADVANCE fill:#e1ffe1
```

## Impact Scoring System

```mermaid
graph LR
    EVENT[Event] --> CALC[Calculate Components]

    CALC --> NOV[Novelty<br/>Based on recent<br/>same-type events]
    CALC --> CONF[Conflict<br/>= severity value]
    CALC --> PUB[Publicness<br/>Event publicness]
    CALC --> STAT[Status<br/>NPC status values]
    CALC --> CASC[Cascade Potential<br/>Effects + deltas]

    NOV --> WEIGHT[Weighted Sum]
    CONF --> WEIGHT
    PUB --> WEIGHT
    STAT --> WEIGHT
    CASC --> WEIGHT

    WEIGHT --> SCORE[Impact Score<br/>0.0 - 1.0]

    SCORE --> THRESH{Score >= Threshold?}

    THRESH -->|>= 0.4| CHAT[Enqueue CHAT]
    THRESH -->|>= 0.6| FEED[Enqueue FEED]
    THRESH -->|>= 0.8| NEWS[Enqueue NEWS]
    THRESH -->|< threshold| SKIP[No render job]

    style SCORE fill:#fff4e1
    style CHAT fill:#e1ffe1
    style FEED fill:#e1ffe1
    style NEWS fill:#ffe1e1
```

## Data Models Overview

```mermaid
erDiagram
    EVENTS ||--o{ POSTS : "generates"
    EVENTS ||--o{ MEMORIES : "creates"
    EVENTS }o--|| EVENT_TYPES : "has type"

    NPCS ||--o{ MEMORIES : "has"
    NPCS ||--o{ GOALS : "pursues"
    NPCS ||--o{ RELATIONSHIPS : "from"
    NPCS ||--o{ RELATIONSHIPS : "to"
    NPCS ||--|| NPC_PROFILES : "has"

    EVENTS {
        string id PK
        timestamp sim_ts
        string type
        string place_id FK
        jsonb actors
        jsonb targets
        float publicness
        float severity
        jsonb payload
    }

    POSTS {
        int id PK
        timestamp created_at
        string channel
        string author_id FK
        string source_event_id FK
        string tone
        text text
        jsonb tags
        string safety_notes
    }

    NPCS {
        string id PK
        string name
        string type
        jsonb meta
    }

    RELATIONSHIPS {
        string from_npc FK
        string to_npc FK
        int trust
        int respect
        int affection
        int jealousy
        int fear
        jsonb grievances
        jsonb debts
    }

    MEMORIES {
        int id PK
        string npc_id FK
        string event_id FK
        float importance
        string summary
        timestamp created_at
    }
```

## Data Flow Details

### 1. Engine Seeding (Startup)

1. Engine checks if DB is empty (no entities exist)
2. If empty, loads from catalog:
   - **Places:** Inserts location entities (sauna, cafe, shop, etc.)
   - **NPCs:** Inserts NPC entities with profiles (persona, values, archetypes)
   - **Relationships:** Initializes relationship edges (trust, respect, affection, etc.)
   - **Goals:** Seeds initial NPC goals (short/long horizon)
3. Injects **Day 1 seed events** from catalog
4. Each event is processed (inserted, effects applied, render jobs enqueued)

### 2. Continuous Simulation (Post-Day 1)

1. **Tick loop** runs every `SIM_TICK_MS` milliseconds (default 1000ms)
2. Every 10 ticks (~10 seconds), **routine event injector** generates:
   - Selects NPC deterministically via round-robin
   - Chooses event template (LOCATION_VISIT, SMALL_TALK, CUSTOMER_INTERACTION) via seeded RNG
   - Matches place by type (sauna/beach, cafe, shop)
3. Event is **processed** (same pipeline as Day 1 events)
4. `sim_ts` advances by `SIM_TICK_MS`

### 3. Event Processing Pipeline

For each event:

1. **Insert:** Write to `events` table with `sim_ts`
2. **Effects:** Apply `event_type.effects`:
   - Create episodic memories for involved NPCs
   - Update relationships (trust, respect, affection, jealousy, fear)
   - Add/remove grievances
3. **Impact:** Calculate impact score (0.0-1.0) using:
   - Novelty (inverse frequency of event type in last 24h)
   - Conflict (= severity)
   - Publicness (event publicness value)
   - Status (average status of involved NPCs)
   - Cascade potential (based on relationship deltas and effects)
4. **Render Jobs:** For each `event_type.render.default_channels`:
   - If `impact >= threshold[channel]`, enqueue to Redis:
     - `{channel, author_id, source_event_id, prompt_context}`

### 4. Content Generation (Workers)

1. **Pop job** from Redis render queue
2. **Load prompt template** from catalog (future: currently using hardcoded prompts)
3. **Build prompt** with event context, NPC profile, and channel requirements
4. **Call LLM Gateway:** `POST /generate`
   - Gateway calls llama.cpp server
   - Validates JSON response
   - Extracts `{tone, text, tags}`
5. **Persist:** Write to `posts` table
6. **Available:** Post is now readable via API `/posts`

### 5. LLM Gateway Responsibilities

- **Single adapter boundary** for all LLM calls
- **Provider abstraction:** Currently supports llama.cpp, designed for vLLM/OpenAI
- **Endpoint fallback:** Tries `/v1/chat/completions` → `/v1/completions` → `/completion`
- **System message merging:** Some models don't support system role, merges into user message
- **JSON extraction:** Uses regex to extract JSON from responses
- **Schema validation:** Ensures response has required fields, provides fallbacks
- **Future:** Caching, repair logic, prompt compression

## Determinism

- All simulation randomness must be seeded via env `SIM_SEED` and logged in events.
- LLM output must not affect truth events; only actions/text derived from events.
- Replay should be possible from `events` + `world_snapshots`.
- RNG is threaded through tick loop to ensure reproducibility.

## Canonical Contracts

Primary runtime source: `packages/shared/data/event_types.json`.
It contains:
- moderation rules + rate limits
- places
- npc profiles + goals + triggers
- relationship initialization
- event types catalog (payload schemas, effects, default render channels)
- prompt templates and Day 1 seed events

Archived specs are in `docs/archive/` for reference only.

## Configuration

Key environment variables (see `koivulahti/infra/.env`):

- **`SIM_SEED`:** Random seed for deterministic simulation (default: 1234)
- **`SIM_TICK_MS`:** Milliseconds per simulation tick (default: 1000)
- **`IMPACT_THRESHOLD_FEED`:** Impact threshold for FEED posts (default: 0.6)
- **`IMPACT_THRESHOLD_CHAT`:** Impact threshold for CHAT posts (default: 0.4)
- **`IMPACT_THRESHOLD_NEWS`:** Impact threshold for NEWS posts (default: 0.8)
- **`LLM_SERVER_URL`:** llama.cpp server URL (e.g., `http://llm-server-cpu:8080`)
- **`LLM_MODEL_PATH`:** Path to GGUF model file in container
- **`DATABASE_URL`:** PostgreSQL connection string
- **`REDIS_URL`:** Redis connection string

