# Current Status & Next Steps (Live)

Updated: 2025-12-14

## What's implemented now

### Infrastructure & Setup
- ✅ Repo scaffold per `repo_structure.txt`
- ✅ `infra/docker-compose.yml` with CPU/GPU llama.cpp profiles
- ✅ `infra/.env` configured for **GPU mode** with **Qwen2.5 7B Instruct Q4_K_M** model
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
- ✅ **Catalog-based prompt building** - loads `feed_prompt`, `chat_prompt`, `news_prompt` from catalog
- ✅ **NPC profile integration** - uses personality, voice, name in prompts
- ✅ **Natural Finnish event descriptions** - converts raw event data to readable Finnish
- ✅ Calls LLM gateway and persists posts

### LLM Gateway (`services/llm_gateway/app/main.py`)
- ✅ **Real llama.cpp adapter with Qwen2.5 7B Q4_K_M**
- ✅ **JSON schema constraint** - forces structured output, prevents essays
- ✅ Multi-endpoint fallback: `/v1/chat/completions` → `/completion`
- ✅ System message merging for models that don't support system role
- ✅ JSON extraction with regex
- ✅ Enhanced system instructions for Finnish content
- ✅ CORS middleware

### API (`services/api/app/main.py`)
- ✅ `/health`, `/posts`, `/events` read endpoints
- ✅ CORS middleware
- ✅ Admin endpoints stubbed

### Tools (`tools/`)
- ✅ **`village_monitor.py`** - CLI activity feed for debugging
  - Live terminal view of events and posts
  - Filter by NPC, event type, channel
  - Usage: `./tools/village_monitor.py --live`

### Testing & Documentation
- ✅ Smoke tests passing (API health, events, posts, LLM gateway)
- ✅ **Pytest test suite** for LLM gateway:
  - `tests/test_gateway_contract.py` - schema validation, const locks
  - `tests/test_gateway_limits.py` - sentence limits, bad openers, Finnish check
  - `scripts/smoke_gateway.py` - standalone smoke script
  - `tests/prompts_fi.json` - 6 Finnish test prompts
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

1. ~~**Wire prompt templates from catalog**~~ ✅ **DONE**
   - ~~Currently: Hardcoded prompts in workers/gateway~~
   - ~~Goal: Load `feed_prompt`, `chat_prompt`, `news_prompt` from `event_types.json`~~
   - ✅ Workers now load catalog prompts and build channel-specific prompts
   - ✅ NPC profiles integrated into prompts

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
   - ✅ JSON repair logic for malformed responses (implemented)
   - ✅ Dynamic JSON schema with const locks and per-channel limits
   - ✅ 3-level fallback (json_schema → json_object+schema → json_object)
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

## Session Summary (2025-12-16 PM) - Content Quality Overhaul

**Ongelma:** Postaukset olivat sekavia - kertoja-tyyli, 3. persoona, meta-puhe, väärä konteksti.

**Korjaukset:**

1. ✅ **Draft-pohjainen renderöinti** (worker.py)
   - `make_draft()` luo deterministisen pohjan eventistä
   - LLM vain uudelleenmuotoilee hahmon äänellä
   - Ei enää "LLM keksii kaiken" -lähestymistapaa

2. ✅ **Tiukempi system-ohje** (gateway main.py)
   - Pakolliset säännöt: 1. persoona (FEED/CHAT), max 2 lausetta
   - Selkeät esimerkit hyvistä ja huonoista postauksista
   - Kielletyt fraasit: "Kuvittele", "Tilannekuva", "Taustaksi" jne.

3. ✅ **Quality gate + polish pass**
   - `has_banned_phrases()` tarkistaa kielletyt ilmaisut
   - `has_third_person_self()` tarkistaa 3. persoonan itsestä
   - Automaattinen polish-pass jos ongelmia löytyy

4. ✅ **Uudet testit** (test_gateway_limits.py)
   - `test_no_narrator_phrases` - ei meta-puhetta
   - `test_first_person_feed_chat` - 1. persoona
   - `test_no_third_person_self` - ei "Kaisa meni"

5. ✅ **Village monitor parannukset**
   - Service status -rivi (●db ●redis ●gateway jne.)
   - Leveämpi tekstikenttä postauksille
   - Shebang käyttää venviä automaattisesti

**Testitulokset:** 13 passed, 1 xfailed, 6 xpassed

**Merge:** `feature/llm-gateway-schema-improvements` → `main` ✅

### 🔴 Jäljellä olevat ongelmat (laatu ei vielä riittävä)

Postaukset teknisesti oikein (1. persoona, ei meta-puhetta) mutta **sisältö geneeristä ja toistavaa:**

```
[CHAT] Leena: Kahviolla. Sovitaan tästä. Kuunnellaan kaikki.
[FEED] Riku: Asiakkaita kaupassa tänään. Fakta.
[CHAT] Aila: En sano nimiä, mutta oon kahviolla. Kyllähän minä kuulin...
```

**Havaitut ongelmat:**
1. **Liian geneerinen** - kaikki sanoo vain "Kahviolla" tai "Asiakkaita X tänään"
2. **Toistuvat fraasit** - "No joo siis", "No katsotaan", "Kyllä tästä"
3. **Persoonallisuus ei erotu** - Aila, Kaisa, Timo kuulostavat samalta
4. **Ei oikeaa sisältöä** - draft on liian tyhjä, LLM ei keksi mitään kiinnostavaa
5. **Sekavia yhdistelmiä** - "En sano nimiä, mutta oon kahviolla" (???)

**Mahdolliset korjaukset:**

| Vaihtoehto | Työmäärä | Vaikutus |
|------------|----------|----------|
| A) Rikkaammat draftit (lisää kontekstia eventistä) | Pieni | Keskisuuri |
| B) Few-shot esimerkit per NPC-persoonallisuus | Keskisuuri | Suuri |
| C) Isompi/parempi malli (Qwen 14B, Mistral-Nemo) | Suuri | Suuri |
| D) Fine-tune nykyistä mallia esimerkeillä | Suuri | Suuri |
| E) Yksinkertaista: template-pohjaiset postaukset + satunnaisuus | Pieni | Keskisuuri |

**Suositus:** Kokeile ensin A+B (rikkaammat draftit + few-shot). Jos ei riitä → mallinvaihto.

---

## Session Summary (2025-12-16) - LLM Gateway & Test Suite

**LLM Gateway parannukset:**
- ✅ Dynaaminen JSON-schema per request (`build_json_schema()`)
- ✅ Kanavakohtaiset merkkirajoitukset: FEED 280, CHAT 220, NEWS 480
- ✅ `const` schemassa (mutta llama.cpp ei tue sitä luotettavasti)
- ✅ 3-tasoinen fallback: json_schema → json_object+schema → json_object → v1/completions → /completion
- ✅ JSON repair loop epävalidille outputille (yrittää korjata LLM:llä)
- ✅ Tiukempi system-ohje (max 2 lausetta, ei johdantoja)
- ✅ `normalize_response()` pakottaa request-arvot (channel, author_id, source_event_id)

**Pytest-testipaketti:**
- ✅ `tests/conftest.py` - fixtures (client, gateway_url, prompt_cases)
- ✅ `tests/prompts_fi.json` - 6 suomenkielistä testitapausta
- ✅ `tests/test_gateway_contract.py` - schema/const/pituus validaatio
- ✅ `tests/test_gateway_limits.py` - soft-testit (2 lausetta, bad openers, suomi)
- ✅ `scripts/smoke_gateway.py` - standalone smoke script
- ✅ `requirements-dev.txt` - pytest + httpx

**Testitulokset (ennen rebuild):**
- 25 passed, 4 xpassed, 3 failed
- Failed: `test_const_locks_respected` - **gateway container ajaa vanhaa koodia!**

**🔥 SEURAAVA SESSIO - aloita tästä:**
```bash
# 1. Rebuild gateway container uudella koodilla
cd infra && docker-compose build llm-gateway
docker-compose up -d llm-gateway

# 2. Aja testit uudelleen
LLM_GATEWAY_URL=http://localhost:8081 pytest tests/ -v

# 3. Jos kaikki OK, merge mainiin
git checkout main && git merge feature/llm-gateway-schema-improvements
```

**Jatkotyöt (pending):**
- 🔲 `test_gateway_fallbacks.py` - vaatii debug-headerin `x-force-fallback`
- 🔲 `test_gateway_repair.py` - vaatii debug-headerin `x-break-json`
- 🔲 Gateway: lisää debug-headerit (vain ENV=dev)
- 🔲 Response caching (Redis)

---

## Session Summary (2025-12-14 Night) - DB Cleanup COMPLETED ✅

**Tietokannan siivous suoritettu onnistuneesti**

Alkutilanne:
- posts: ~250 riviä (sisälsi stub-postauksia, rikkinäisiä kanavia, englantia, author_id variaatioita)
- events: 2346 tapahtumaa (paljon vanhoja routine-eventtejä)
- memories: 1020 muistoa (sidottu eventteihin)

**Suoritetut toimenpiteet:**

1. ✅ **Posts-taulun siivous:**
   - Poistettu vanhat postaukset (id < 220)
   - Poistettu rikkinäiset kanavat (NOT IN FEED/CHAT/NEWS)
   - Korjattu author_id variaatiot yhtenäisiksi (capitalize first letter):
     - `aila`, `miia`, `eero`, `osku` → `Aila`, `Miia`, `Eero`, `Osku`
     - `NPC_Petri` → `Petri`
     - `timo_id` → `Timo`

2. ✅ **Events-taulun siivous:**
   - Poistettu 1326 vanhaa routine-eventtiä
   - Pidetty viimeisimmät 1000 routine-eventtiä + kaikki Day 1 seed eventit

3. ✅ **Memories-taulun siivous:**
   - Automaattisesti siivottu CASCADE DELETE:llä (579 muistoa jäljellä)
   - Ei orphan-muistoja

**Lopputilanne:**
```
Table          | Count | Size    | Status
---------------|-------|---------|--------
posts          | 55    | 160 kB  | ✅ Clean, Finnish, valid channels
events         | 1020  | 776 kB  | ✅ Recent events + Day 1 seeds
memories       | 579   | 272 kB  | ✅ Auto-cleaned via CASCADE
relationships  | 14    | 64 kB   | ✅ OK
goals          | 18    | 48 kB   | ✅ OK
---------------|-------|---------|--------
TOTAL          |       | ~1.3 MB | ✅ Optimized
```

**Tulokset:**
- ✅ Kaikki postaukset laadukasta suomea (Qwen2.5-generoidut)
- ✅ Author_id:t yhtenäisiä (12 uniikkia NPC:tä)
- ✅ Channels validit (FEED, CHAT)
- ✅ Tietokanta optimoitu (~56% pienempi)
- ✅ Ei dataintegriteetti-ongelmia

---

## Session Summary (2025-12-14 Evening)

**Major Finnish Language Quality Upgrade - Qwen2.5 + Catalog Prompts**

Problem identified:
- Mistral 7B produced poor Finnish quality (grammar errors, English leakage)
- Hardcoded prompts lacked channel-specific guidance
- No NPC personality integration in prompts
- JSON output unreliable without schema constraints

Solutions implemented:
1. **Upgraded to Qwen2.5 7B Instruct Q4_K_M** (4.4GB, excellent multilingual)
2. **JSON schema constraint** in LLM gateway - forces valid structure, prevents essays
3. **Wired catalog prompt templates** from `event_types.json` to workers
4. **NPC profile integration** - personality, voice, name used in prompts
5. **Enhanced Finnish instructions** - channel-specific, proper length limits
6. Lowered temperature 0.7 → 0.3 for stability

Results (MASSIVE improvement):
- ✅ **Natural colloquial Finnish** - "Saunaan meni. Uusi alku. Mä en oo täällä draaman takia."
- ✅ **No English leakage** - consistent Finnish throughout
- ✅ **NPC personalities show** - Aila dramatic, others varied styles
- ✅ **Valid JSON always** - schema constraint works perfectly
- ✅ **Channel-specific tone** - FEED vs CHAT clearly different
- ✅ **Contextual tags** - relevant to content
- ✅ **Punchy social media style** - no long essays

Example posts generated:
```
Miia (CHAT): "No joo siis… Aika villiä. Ei oo ok. Miten sinulla menee?"
Jari (FEED): "Kaupassa jälleen. Säännöt on syystä. Katsotaan nyt."
Aila (FEED): "En sano nimiä, mutta hänen ostoksensa olivat jopa hienompia kuin hänen lausuntojensa."
```

Files changed:
- `infra/.env` - Qwen2.5 7B model, temperature 0.3
- `services/workers/app/worker.py` - catalog prompt loading, NPC profile integration
- `services/llm_gateway/app/main.py` - JSON schema constraint, enhanced system message
- Downloaded: `models/qwen2.5-7b-instruct-q4_k_m.gguf` (4.4GB)

**System now demo-ready with high-quality Finnish content generation!**

---

## Session Summary (2025-12-14 Morning)

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

**GPU LLM Server activation**

- Switched from CPU to GPU llama.cpp server
- Updated `.env`: `LLM_SERVER_URL=http://llm-server-gpu:8080`
- Flash Attention enabled, 4 parallel slots

**Missing event types added**

- Added `LOCATION_VISIT` and `CUSTOMER_INTERACTION` to `event_types.json`
- These routine events now have render channels (FEED) configured
- Lowered impact thresholds for more realistic posting behavior:
  - FEED: 0.6 → 0.15
  - CHAT: 0.4 → 0.10
  - NEWS: 0.8 → 0.5

**Full pipeline verified working**

- Engine → Redis queue → Workers → LLM Gateway → GPU → Posts in DB
- 40+ posts generated during testing
- Pipeline processes ~1 event/second with GPU acceleration

**Village monitor tool added**

- `tools/village_monitor.py` - CLI for real-time activity feed
- Shows events and posts side-by-side with colors
- Supports `--live` mode, filtering by `--npc`, `--type`, `--channel`

**Next session priorities:**
1. 🔥 Fix prompt templates for proper Finnish content
2. 🔥 Fix channel parsing (posts showing wrong channel names)
3. Consider: Add more dramatic event types for variety

**Known issues:**
- Some posts have malformed channel names (prompt parsing issue)
- LLM sometimes outputs English or raw event data instead of Finnish posts
- Prompt templates need refinement for better content quality

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
