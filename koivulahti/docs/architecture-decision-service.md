# Decision Service Architecture

> **Experimental and opt-in.** This service currently chooses publishing actions, not legal world actions. It is disabled in the default stack until durable jobs and throughput controls are implemented.

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    KOIVULAHTI STACK                                     │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐           │
│  │   Engine    │────▶│    Redis    │◀────│  Decision   │────▶│   Workers   │           │
│  │             │     │             │     │   Service   │     │             │           │
│  │ (stimulus   │     │ ┌─────────┐ │     │             │     │ (Finnish    │           │
│  │  generator) │     │ │decision │ │     │ (Gemini     │     │  rendering) │           │
│  └─────────────┘     │ │ _jobs   │ │     │  LLM calls) │     └──────┬──────┘           │
│         │            │ └─────────┘ │     └──────┬──────┘            │                  │
│         │            │ ┌─────────┐ │            │                   │                  │
│         │            │ │render   │ │            │                   │                  │
│         │            │ │ _jobs   │ │            │                   │                  │
│         │            │ └─────────┘ │            │                   │                  │
│         │            └─────────────┘            │                   │                  │
│         │                                       │                   │                  │
│         ▼                                       ▼                   ▼                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐          │
│  │                            PostgreSQL                                     │          │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │          │
│  │  │ events   │ │ posts    │ │decisions │ │ entities │ │ memories │        │          │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘        │          │
│  └──────────────────────────────────────────────────────────────────────────┘          │
│                                                                                         │
│  ┌─────────────┐     ┌─────────────┐                                                   │
│  │     API     │     │ LLM Gateway │◀─────────────────────────────┐                    │
│  │  (FastAPI)  │     │  (FastAPI)  │                              │                    │
│  │ :8082       │     │  :8081      │                              │                    │
│  └─────────────┘     └──────┬──────┘                              │                    │
│                             │                                      │                    │
│                             ▼                                      │                    │
│                      ┌─────────────┐                               │                    │
│                      │ llama.cpp   │                               │                    │
│                      │ (GPU/CPU)   │◀──────────────────────────────┘                    │
│                      │ Qwen2.5 7B  │         Workers call for Finnish rendering        │
│                      │ :8080       │                                                    │
│                      └─────────────┘                                                    │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘

                                    EXTERNAL APIS
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐           │
│  │                     Google Gemini API (Decision LLM)                     │           │
│  │                                                                          │           │
│  │  Model: configured with GEMINI_MODEL (default: gemini-3.1-flash-lite)   │           │
│  │  Endpoint: generativelanguage.googleapis.com                            │           │
│  │  Purpose: NPC decision-making (action, intent, emotion, draft)          │           │
│  │  Rate limit: ~6 calls/min (configurable via DECISION_MIN_INTERVAL)      │           │
│  │                                                                          │           │
│  └─────────────────────────────────────────────────────────────────────────┘           │
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐           │
│  │                     Future: Ambient Data Sources                         │           │
│  │                                                                          │           │
│  │  - Open-Meteo (weather)                                                  │           │
│  │  - RSS feeds (Finnish news)                                              │           │
│  │  - Sports APIs (jääkiekko results)                                       │           │
│  │                                                                          │           │
│  └─────────────────────────────────────────────────────────────────────────┘           │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
1. STIMULUS GENERATION (Engine)
   ┌──────────────────────────────────────────────────────────────────┐
   │  Routine events: LOCATION_VISIT, SMALL_TALK, CUSTOMER_INTERACTION│
   │  Ambient events: AMBIENT_WEATHER, AMBIENT_NEWS                   │
   │  Post events: POST_SEEN (chain reactions)                        │
   └──────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
2. DECISION QUEUE (Redis: decision_jobs)
   ┌──────────────────────────────────────────────────────────────────┐
   │  { job_id, npc_id, stimulus: { event_type, payload, actors } }   │
   └──────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
3. DECISION SERVICE (Gemini API)
   ┌──────────────────────────────────────────────────────────────────┐
   │  Context: NPC profile, memories, relationships, recent posts     │
   │  Prompt: Structured decision prompt with persona                 │
   │  Output: { action, intent, emotion, draft, reasoning, confidence}│
   │  Audit: Logged to decisions table                                │
   └──────────────────────────────────────────────────────────────────┘
                                    │
                     ┌──────────────┴──────────────┐
                     │                             │
              action=IGNORE                 action=POST_*
                     │                             │
                     ▼                             ▼
              (no action)              4. RENDER QUEUE (Redis: render_jobs)
                                       ┌──────────────────────────────┐
                                       │  { author_id, channel,       │
                                       │    decision: { draft, ... } }│
                                       └──────────────────────────────┘
                                                   │
                                                   ▼
                                       5. WORKERS (llama.cpp)
                                       ┌──────────────────────────────┐
                                       │  Finnish text rendering      │
                                       │  NPC voice/personality       │
                                       │  Qwen2.5 7B local model      │
                                       └──────────────────────────────┘
                                                   │
                                                   ▼
                                       6. POSTS TABLE (PostgreSQL)
                                       ┌──────────────────────────────┐
                                       │  { author_id, channel, text, │
                                       │    source_event_id, ... }    │
                                       └──────────────────────────────┘
```

## Docker Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `postgres` | postgres:16 | internal | Database |
| `redis` | redis:7 | internal | Job queues |
| `engine` | koivulahti-engine | - | Event generation |
| `decision-service` | koivulahti-decision-service | - | Gemini LLM decisions |
| `workers` | koivulahti-workers | - | Finnish rendering |
| `llm-gateway` | koivulahti-llm-gateway | internal | fake/llama.cpp provider boundary |
| `llm-server-gpu` | llama.cpp:server-cuda | internal | Local LLM |
| `api` | koivulahti-api | 127.0.0.1:8082 | REST API |
| `ambient-worker` | koivulahti-ambient-worker | - | External data fetch |

## Configuration

### Environment Variables (.env)

```bash
# Decision Service
DECISION_SERVICE_ENABLED=true
DECISION_QUEUE=decision_jobs
DECISION_MIN_INTERVAL=10.0    # Rate limit (seconds between calls)

# Gemini API: keep these only in the ignored infra/.env file
GEMINI_API_KEY=<set-in-private-env>
GEMINI_MODEL=gemini-3.1-flash-lite

# Feature flags
# - true:  Engine → Decision Service (Gemini) → Workers (llama.cpp)
# - false: Engine → Workers (old hash-based appraisal)
```

### Provider configuration

The Decision Service uses the single `packages/shared/gemini_client.py` adapter. Select a supported model through `GEMINI_MODEL`; do not add provider-specific imports to the service loop. Credentials are sent in the `x-goog-api-key` header so they do not appear in request URLs.

## Monitoring

```bash
# Full pipeline view
./tools/village_monitor.py --live

# Output:
# ╭─ KOIVULAHTI ─╮
# │ Events: 3000  Posts: 1300  Decisions: 300             │
# │ Gemini 5min: 20 active | ~1300ms | no errors          │
# │ ●db ●redis ●llm ●gateway ●api ●engine ●decision ●workers │
# ╰─────────────╯
#      Events              Decisions              Posts
#  SMALL_TALK  →  aila POST_CHAT 🤔  →  "Kuulin että..."
```
