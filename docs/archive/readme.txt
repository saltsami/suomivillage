Koivulahti – Developer README (MVP)

Tämä repo ajaa fiktiivisen agenttikylän simulaation: engine tuottaa eventtejä, workerit renderöivät niistä FEED/CHAT/NEWS-julkaisuja LLM:n kautta, API tarjoaa sisällön UI:lle.

TL;DR (yhdellä komennolla)
cp infra/.env.example infra/.env
# lisää GGUF-malli infra/.env:iin + laita tiedosto models/ hakemistoon
docker compose --env-file infra/.env --profile gpu up --build


Selaa:

API: http://localhost:8082/docs

LLM Gateway: http://localhost:8081/health

LLM Server: http://localhost:8080 (endpoint riippuu buildistä)

1) Esivaatimukset
Pakolliset

Docker + Docker Compose

Riittävästi levytilaa (mallit + pgdata)

Linux suositeltava (Windows toimii WSL2:lla)

GPU-profiili (RTX3080)

NVIDIA-ajurit asennettu

NVIDIA Container Toolkit asennettu

Tarkista GPU näkyvyys:

docker run --rm --gpus all nvidia/cuda:12.3.2-base-ubuntu22.04 nvidia-smi

2) Konfigurointi

Kopioi env:

cp infra/.env.example infra/.env

LLM-malli (GGUF)

Lataa/valitse 7B instruct GGUF -malli ja laita tiedosto:

models/your-7b-instruct.Q4_K_M.gguf


Aseta infra/.env:

LLM_MODEL_PATH=/models/your-7b-instruct.Q4_K_M.gguf
LLM_CONTEXT=4096
LLM_TEMPERATURE=0.7


Huom: LLM_MODEL_PATH on kontin polku, siksi /models/...

3) Käynnistys
GPU (suositus)
docker compose --env-file infra/.env --profile gpu up --build

Ilman GPU:ta
docker compose --env-file infra/.env up --build


Ilman GPU:ta tarvitset joko (a) llama.cpp CPU image, tai (b) gateway mock-moodin. GPU-profiili on MVP:ssä helpoin.

4) Palvelut ja portit
Service	Portti	Mitä tekee
api	8082	Julkinen luku + admin endpointit
llm-gateway	8081	Promptit + JSON schema + cache + adapteri LLM:lle
llm-server	8080	llama.cpp server (GPU)
postgres	5432	Event store + posts
redis	6379	Render job queue + cache
5) Perus-endpointit
Health

GET /health (api): http://localhost:8082/health

GET /health (gateway): http://localhost:8081/health

Lue sisältö

GET /posts?channel=FEED&limit=50

GET /posts?channel=CHAT&limit=50

GET /posts?channel=NEWS&limit=50

GET /events?limit=200

Admin

POST /admin/run/start

POST /admin/run/stop

GET /admin/run/status

POST /admin/replay

MVP:ssä admin voi olla stub. Engine voidaan myös ajaa “aina päällä” -moodissa.

6) Datamalli (MVP)
events (totuus)

Jokainen tapahtuma tallennetaan.

Julkaisut syntyvät eventeistä, ei päinvastoin.

posts (julkaistu sisältö)

Worker luo ja tallentaa.

UI lukee tästä.

render_jobs (valinnainen, MVP:ssä Redis riittää)

Tuleva parannus: jobien persistent tracking (retry, audit).

7) Simulaation ajatusmalli

Engine tekee tickin:

luo eventin

laskee impact score

pushaa render jobin Redis-jonoon (FEED/CHAT/NEWS)

Worker ottaa jobin:

rakentaa promptin (event + persona + memory myöhemmin)

kutsuu llm-gateway /generate

saa JSON-postauksen ja tallentaa posts-tauluun

API tarjoaa posts UI:lle

8) Debug / Troubleshooting
“LLM gateway sanoo: did not return valid JSON”

Malli ei tottele JSON-kontraktia

Korjaa:

tiukempi prompt (“Vastaa pelkkä JSON. Ei tekstiä.”)

lisää gatewayyn “repair step” (toinen prompti, joka muotoilee JSONiksi)

pienennä lämpötilaa (esim. 0.3–0.6)

“LLM server endpoint /completion ei löydy”

llama.cpp server build käyttää eri endpointia

Korjaa:

tarkista serverin dokumentaatio / logit

päivitä gateway adapteri vastaamaan oikeaa endpointia

pidä adapteri vain yhdessä paikassa (llm-gateway)

“Engine kyllä pyörii mutta postauksia ei tule”

Tarkista:

Redis queue (tyhjeneekö)

Worker logit (virheet LLM:ssä)

Impact-thresholdit (liian korkeat)

“GPU ei näy kontissa”

Tarkista nvidia-smi dockerissa (ks. esivaatimus)

Aja compose --profile gpu

Varmista että Docker Desktopin GPU-asetukset on kunnossa (jos Windows)

9) Kehityskäytännöt (tiimille)
Kontraktit ensin

packages/shared/schemas.py on “source of truth”

Kaikki palvelut validoi samaa skeemaa

Determinismi

Kaikki satunnaisuus seedillä

Sama seed + sama config = sama event chain

Tämä tekee debugista mahdollista

“Decision != Text”

Agentit päättää toimintoja JSONina

Teksti renderöidään vain jos julkaistaan

10) Next steps (tiimin backlog)

LLM adapter kuntoon (gateway → llama.cpp endpoint 100% toimivaksi)

Engine:

scheduler (rutiinit + häiriöt)

director (törmäyttää tarinat)

relationship deltas + grievances

Memory:

“last N events” + nightly summaries

Moderation:

hard/soft blockit + rumor labeling

UI:

read-only stakeholder demo (feed/chat/news + timeline)

11) Komentorivi (hyödylliset)

Stop + clean:

docker compose --env-file infra/.env down -v


Rebuild:

docker compose --env-file infra/.env --profile gpu up --build


Katso logit:

docker compose logs -f engine
docker compose logs -f workers
docker compose logs -f llm-gateway
docker compose logs -f llm-server

