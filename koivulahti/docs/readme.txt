Koivulahti – Developer README (MVP, live)

Koivulahti on fiktiivinen agenttikylä: simulaatio tuottaa deterministisiä eventtejä (totuus), ja sisältökerros renderöi niistä FEED/CHAT/NEWS‑julkaisuja LLM‑gatewayn kautta. Tämä README kuvaa nykyisen scaffoldin ja miten saat sen pystyyn.

TL;DR
1. Mene infraan: `cd koivulahti/infra`
2. Kopioi env: `cp .env.example .env`
3. Laita GGUF‑malli kansioon `koivulahti/models/` ja päivitä `.env`:
   - `LLM_MODEL_PATH=/models/your-7b-instruct.Q4_K_M.gguf`
4. Käynnistä:
   - GPU (RTX3080): `docker compose --env-file .env --profile gpu up --build`
   - CPU fallback: `docker compose --env-file .env --profile cpu up --build`

LLM‑serverin oletus‑imagit tulevat `ghcr.io/ggml-org/llama.cpp`‑repossa (`server` / `server-cuda`). Jos haluat täyden toistettavuuden, pinnaa digest:
  `docker pull ghcr.io/ggml-org/llama.cpp:server-cuda`
  `docker image inspect ghcr.io/ggml-org/llama.cpp:server-cuda --format='{{index .RepoDigests 0}}'`
  -> aseta `.env`:iin esim. `LLM_SERVER_IMAGE_GPU=ghcr.io/ggml-org/llama.cpp@sha256:<DIGEST>`.

Selaa:
- API: http://localhost:8082/docs
- LLM Gateway health: http://localhost:8081/health
- LLM Server (llama.cpp): http://localhost:8080

1) Esivaatimukset
- Docker + Docker Compose
- Levytilaa (mallit + `pgdata`)
- Linux suositeltava (Windows toimii WSL2:lla)

GPU‑profiili (valinnainen mutta suositus MVP:lle):
- NVIDIA‑ajurit + NVIDIA Container Toolkit
- Tarkista GPU näkyvyys:
  `docker run --rm --gpus all nvidia/cuda:12.3.2-base-ubuntu22.04 nvidia-smi`

2) Konfigurointi
- Env:
  `cd koivulahti/infra && cp .env.example .env`
- LLM‑malli:
  - Lataa 7B instruct GGUF ja laita hostille: `koivulahti/models/your-7b-instruct.Q4_K_M.gguf`
  - `.env` sisällä malli näkyy kontin polkuna `/models/...`.
- LLM‑serveri:
  - GPU‑ajossa: `LLM_SERVER_URL=http://llm-server-gpu:8080`
  - CPU‑ajossa: `LLM_SERVER_URL=http://llm-server-cpu:8080`
- Simulaatio:
  - `SIM_SEED` määrää determinismin.
  - `IMPACT_THRESHOLD_*` kontrolloi mitä julkaistaan kanaviin.

3) Käynnistys ja pysäytys
Käynnistä infra‑kansiosta:
- GPU: `docker compose --env-file .env --profile gpu up --build`
- CPU: `docker compose --env-file .env --profile cpu up --build`
- `docker compose --env-file .env down -v` (stop + clean)

4) Palvelut ja portit
Service | Portti | Mitä tekee
---|---|---
`api` | 8082 | Julkinen luku + admin stubit
`llm-gateway` | 8081 | Promptit + JSON‑kontrakti + adapteri LLM:lle
`llm-server-cpu` / `llm-server-gpu` | 8080 | llama.cpp server (valitse profiililla cpu/gpu)
`postgres` | 5432 | Event store + world taulut + posts
`redis` | 6379 | Render job queue + cache

5) Nykyinen ajomalli (mitä tapahtuu nyt)
- Canonical data on `packages/shared/data/event_types.json`.
- Engine:
  - Seedaa DB:n tyhjästä (NPC:t, paikat, suhteet, goals).
  - Ajaa `day1_seed_scenario` eventit kerran ja tallentaa ne `events`‑tauluun.
  - Laskee yksinkertaisen impactin ja pushaa render‑jobit Redis‑jonoon eventtyypin `render.default_channels` mukaan.
- Worker:
  - Poppailee jobit, hakee author‑profiilin `npc_profiles`‑taulusta, rakentaa promptin ja kutsuu gatewayta.
  - Tallentaa palautetun postauksen `posts`.
- Gateway:
  - Tällä hetkellä stub: `/generate` palauttaa deterministisen placeholder‑JSONin. Kun adapteri on tehty, tänne tulee llama.cpp‑kutsu + JSON‑repair.

6) Perus‑endpointit
Health:
- API: `GET http://localhost:8082/health`
- Gateway: `GET http://localhost:8081/health`

Sisältö:
- `GET /posts?limit=50`
- `GET /events?limit=200`

Admin (stub):
- `POST /admin/run/start`
- `POST /admin/run/stop`
- `GET /admin/run/status`
- `POST /admin/replay`

7) Datamalli (live)
Migrations:
- `migrations/001_init.sql`: `events`, `world_snapshots`, `render_jobs`, `posts`
- `migrations/002_kickoff_tables.sql`: `entities`, `npc_profiles`, `relationships`, `memories`, `goals`

8) Debug / Troubleshooting
“Postauksia ei tule”
- Tarkista `docker compose logs -f engine workers`.
- Tarkista Redis‑jono: impact‑thresholdit voivat olla liian korkeat.

“Gateway palauttaa vain stub‑tekstiä”
- Tämä on odotettua MVP‑scaffoldissa. Tee llama.cpp adapteri `services/llm_gateway/app/main.py` ja kytke schema‑validointi.

“LLM server endpoint ei löydy”
- llama.cpp endpoint vaihtelee buildistä. Päivitä adapteri vain gatewayyn, ei workereihin.

“LLM server image tag ei löydy”
- Käytä ggml‑org `server`/`server-cuda` tageja tai overridea `.env`:issä `LLM_SERVER_IMAGE_CPU`/`LLM_SERVER_IMAGE_GPU`.

“GPU ei näy kontissa”
- Aja `--profile gpu` ja varmista `nvidia-smi` dockerissa.

9) Kehityskäytännöt
- Kontraktit ensin: `event_types.json` + `packages/shared/schemas.py` ovat totuus.
- Determinismi ennen sisältöä: sama seed → sama event‑ketju.
- “Single gateway adapter”: kaikki mallikohtaiset erot vain `llm-gateway`‑palveluun.

10) Mihin jatketaan
Katso tarkempi lista ja session‑suunnitelma: `docs/status-and-next.md`.
Lyhyesti: kytke prompt‑templaatit → tee gateway adapteri + JSON‑repair → lisää engineen tick + efektit + replay.
