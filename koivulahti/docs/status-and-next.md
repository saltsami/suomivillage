# Current Status & Next Steps (Live)

Updated: 2025-12-14

## What's implemented now

### Infrastructure & Setup
- ✅ Repo scaffold per `repo_structure.txt`
- ✅ `infra/docker-compose.yml` with CPU/GPU llama.cpp profiles
- ✅ `infra/.env` configured for CPU mode with Mistral 7B model
- ✅ Migrations: `001_init.sql` (events/posts/jobs), `002_kickoff_tables.sql` (entities/profiles/relationships/memories/goals)

### Shared Packages
- ✅ `packages/shared/settings.py`, `db.py`, `schemas.py`
- ✅ `packages/shared/data_loader.py` loads canonical catalog
- ✅ `packages/shared/data/event_types.json` in-tree

### Engine (`services/engine/app/runner.py`)
- ✅ Seeds DB from catalog if empty (places, NPCs, profiles, relationship edges, goals)
- ✅ Injects Day 1 seed events (17 events from catalog)
- ✅ **Continuous simulation loop** with deterministic tick scheduler
- ✅ **Post-Day1 routine event injector**:
  - Generates events every 10 ticks (~10 seconds)
  - NPC round-robin selection (deterministic)
  - 3 event types: LOCATION_VISIT, SMALL_TALK, CUSTOMER_INTERACTION
  - Place matching by type (sauna/beach, cafe, shop)
  - **Restart resilient**: Resumes from last tick index in DB
- ✅ **Impact scoring system** (novelty, conflict, publicness, status, cascade potential)
- ✅ **Event effects** applied to relationships and memories
- ✅ Enqueues render jobs to Redis based on impact thresholds

### Workers (`services/workers/app/worker.py`)
- ✅ Pops Redis jobs, fetches author profile
- ✅ Builds prompts from event context
- ✅ Calls LLM gateway and persists posts

### LLM Gateway (`services/llm_gateway/app/main.py`)
- ✅ **Real llama.cpp adapter** (not stub!)
- ✅ Multi-endpoint fallback: `/v1/chat/completions` → `/v1/completions` → `/completion`
- ✅ System message merging for models that don't support system role
- ✅ JSON extraction with regex
- ✅ Schema validation with fallbacks
- ✅ CORS middleware

### API (`services/api/app/main.py`)
- ✅ `/health`, `/posts`, `/events` read endpoints
- ✅ CORS middleware
- ✅ Admin endpoints stubbed

### Testing & Documentation
- ✅ Smoke tests passing (API health, events, posts, LLM gateway)
- ✅ **Comprehensive documentation**:
  - README.md with quick start guide
  - architecture.md with 5 Mermaid diagrams (system, event flow, tick flow, impact scoring, data models)
  - contracts.md (database schema, API contracts)
  - status-and-next.md (this file)

## How to run

See [README.md](../../README.md) for detailed quick start guide.

**Quick reference:**
```bash
cd koivulahti/infra
docker-compose --profile cpu up -d  # or --profile gpu
docker-compose logs engine -f
curl http://localhost:8082/events?limit=5
```

## Remaining work (prioritized)

### 🔥 Critical Path (Demo-ready)

1. **Wire prompt templates from catalog**
   - Currently: Hardcoded prompts in workers/gateway
   - Goal: Load `feed_prompt`, `chat_prompt`, `news_prompt` from `event_types.json`
   - Workers build prompts consistently per channel

2. **Daily NEWS digest**
   - Once per sim day, generate NEWS_PUBLISHED event
   - Pick top N events by impact score
   - Aggregate into daily village news post

3. **Nightly memory summaries**
   - Per NPC, write 1 summary memory per sim day
   - Compact older episodic memories (keep recent + important)

4. **Improve routine injector**
   - Add more event variety (conflicts, discoveries, transactions)
   - Goal-driven event selection (NPCs pursue goals)
   - Time-of-day awareness (morning routines, evening social)

### 🛡️ Production Quality

5. **Moderation + rate limits**
   - Apply `moderation_rules` from catalog before insert
   - Enforce `rate_limits` per channel/author
   - Block or flag problematic content

6. **World snapshots for replay**
   - Persist `world_snapshots` at sim day boundaries
   - Add replay script/endpoint
   - Verify determinism by replaying from seed

7. **Better LLM gateway**
   - JSON repair logic for malformed responses
   - Response caching (Redis)
   - Prompt compression for long contexts

### 🤖 Agent Decision MVP (Next Phase)

8. **NPC perception & retrieval**
   - Event-triggered perception (NPCs notice events)
   - Scheduled perception windows
   - Memory retrieval for decision context

9. **Action decision loop**
   - LLM outputs action JSON per `action_schema`
   - Engine validates action against rules
   - Emit resulting events deterministically

10. **Director system**
    - Narrative arc injectors
    - Tension/pacing management
    - Conflict escalation/resolution

### 📊 Admin & UI (Later)

11. **Admin endpoints**
    - POST `/admin/run/start`, `/admin/run/stop`
    - POST `/admin/seed/reset`
    - POST `/admin/replay?from_tick=X`
    - GET `/admin/metrics` (events/posts counts, NPC states)

12. **Read-only village UI**
    - Event timeline
    - NPC profiles & relationships
    - Live feed/chat/news streams
    - Relationship graph visualization

## Session Summary (2025-12-14)

**Bugfix: Engine restart event generation**

Problem discovered:
- Simulation had stopped generating events ~2 days ago
- Engine was running but no new events in database
- Root cause: DNS failure crashed engine, on restart `tick_index` started from 0
- Event IDs like `evt_routine_{tick}_{npc}` already existed in DB
- `ON CONFLICT DO NOTHING` silently rejected all new events

Fix applied (`runner.py`):
- Added `fetch_latest_tick_index()` to query max tick from existing events
- Engine now resumes from `last_tick + 1` instead of 0
- RNG state advanced to match resumed position for determinism
- Log now shows `resume_tick=N` on startup

Verification:
- Events resuming from tick 19141 (was stuck at 19140)
- New events confirmed in database with current timestamps
- Commit: `91e1bcf Fix engine restart not generating new events`

---

## Session Summary (2025-12-12)

**Major accomplishments:**
- ✅ Implemented post-Day1 continuous simulation with routine event injector
- ✅ Fixed CORS issues in API and gateway
- ✅ Configured llama.cpp with CPU/GPU profiles
- ✅ Integrated real LLM adapter (no longer stub!)
- ✅ All smoke tests passing
- ✅ Comprehensive documentation with Mermaid diagrams
- ✅ README with quick start guide

**Technical details:**
- Routine injector generates events every 10 ticks (configurable)
- Deterministic NPC round-robin + seeded RNG for variety
- Impact scoring working (0.23-0.51 range observed)
- Events → memories → relationships pipeline functional
- 100+ routine events generated in test run

**Ready for next session:**
- System is demo-ready for "Day 1 → continuous sim" showcase
- Next: Wire catalog prompts for better content quality
- Consider: Daily NEWS digest for narrative structure
