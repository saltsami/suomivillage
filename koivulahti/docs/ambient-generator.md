# Ambient Event Generator (Koivulahti)

## Tavoite
Tuottaa maailmaan "ambient" ärsykkeitä ulkopuolisesta datasta (sää, uutisotsikot),
joihin NPC:t reagoivat omalla tavalla (feed/chat/news). Tavoite on luoda luontevia
ketjureaktioita ilman käsinkirjoitettua sisältöä.

## Periaatteet
- Ambient-data on "ärsyke", ei tarina.
- NPC:n reaktio = (havaitse -> arvioi -> intent -> postaa/vastaa/toimii).
- Ulkoinen data snapshotataan, jotta sama sim-päivä voidaan replayata identtisesti.
- Jakelu on deterministinen: sama ambient_event_id + npc_id -> sama "näki / ei nähnyt" päätös.

## Komponentit

### A) Ambient Collector (worker)
Hakee ulkoa:
- Weather (1–2x / sim-päivä / alue)
- News (N otsikkoa / sim-päivä)
- Sports (N otsikkoa / sim-päivä)

Tallentaa:
- raw snapshot (ambient_sources)
- normalisoidut ambient_eventit (ambient_events)
- ilmoittaa enginelle (redis channel / DB flag)

### B) Engine Distributor
- poimii uudet ambient_eventit, joita ei ole vielä jaettu
- laskee kohderyhmän (kaikki / segmentti / "someaktiiviset" / "kiinnostusprofiili")
- luo NPC-kohtaiset AMBIENT_SEEN eventit (events-tauluun)
- merkitsee jakelun tehdyksi (ambient_deliveries)

### C) NPC Appraisal + Intent (heuristiikka)
- tulkitsee AMBIENT_SEEN payloadin (topic, intensity, sentiment, facts)
- tuottaa intentin:
  - POST_FEED / POST_CHAT / IGNORE / REPLY_TO_POST / GO_DO_SOMETHING
- cooldownit estää spämmin

### D) Render Pipeline
- Engine/agent tuottaa DRAFT-tekstin (faktoihin sidottu)
- LLM tekee vain "rewrite in voice" + max pituus

## Event-tyypit
- AMBIENT_WEATHER
- AMBIENT_NEWS_HEADLINE
- AMBIENT_SPORTS_HEADLINE
- AMBIENT_SEEN   (NPC-kohtainen)

## Normalisoitu ambient_event (JSON)
Common fields:
- id (stable)
- type
- sim_date
- region
- topic (enum)
- intensity 0..1
- sentiment -1..1
- confidence 0..1
- expires_at
- payload:
  - summary_fi (1–2 lausetta)
  - facts (1–3 bulletia)
  - link (optional)
  - source: {provider, raw_id}

## Determinismi & Replay
- ambient_sources.raw_json tallennetaan
- ambient_events.normalized_json tallennetaan
- Distributor käyttää determinististä hashia:
  - seen = (hash(ambient_id + npc_id) mod 100) < visibility_pct
- "visibility_pct" voi tulla eventistä tai NPC:n someaktiivisuudesta

## Rate control (jottei tule 200 postausta päivässä)
- Weather: max 2 event/päivä
- News: max 3–8 event/päivä (koko kylä)
- Sports: max 1–3 event/päivä
- NPC cooldown:
  - FEED max 1 / 2h
  - CHAT max 2 / 1h
  - reply max 3 / 2h

## Esimerkki: lumisadeketju
1) AMBIENT_WEATHER(topic=weather_snow, intensity=0.8)
2) Distributor -> AMBIENT_SEEN(Noora, Sanni, Kaisa...)
3) Appraisal:
   - Noora (romantic) -> POST_FEED "Lunta sataa, onpa kaunista"
   - Kaisa (practical) -> REPLY/POST "Ja taas lumityöt..."
4) Post julkaistaan -> POST_PUBLISHED -> muille POST_SEEN -> jatkokeskustelu

## Tietokantarakenne

```sql
-- Raw API responses (replay-friendly)
ambient_sources (
  id, created_at, provider, region, request, response
)

-- Normalized events ready for distribution
ambient_events (
  id (stable), sim_date, type, region, topic, intensity, sentiment, confidence,
  expires_at, source_ref, payload
)

-- Tracks which NPCs have received which ambient events
ambient_deliveries (
  id, ambient_event_id, npc_id, delivered_at
)
```

## API Endpoints (tulevat)

- GET `/ambient/events?sim_date=X` - list ambient events for date
- GET `/ambient/sources?provider=X` - list raw sources
- POST `/admin/ambient/inject` - manually inject test ambient event

## Seuraavat vaiheet

1. ✅ Migraatio `003_ambient_tables.sql`
2. ✅ Ambient worker stubi (mock data)
3. ✅ Engine distributor (AMBIENT_SEEN jakelu)
4. ✅ NPC appraisal matriisi (topic -> intent mapping)
5. 🔲 Oikeat fetcherit (Open-Meteo, RSS)
6. 🔲 Rate limiting ja cooldowns
7. 🔲 Response-to-post threading
