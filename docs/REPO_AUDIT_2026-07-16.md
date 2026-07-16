# Suomivillage / Koivulahti: repo-, tuote- ja jatkamisauditointi

**Päivä:** 16.7.2026<br>
**Auditoitu versio:** `feature/ambient-event-generator` @ `81a35b5`<br>
**Auditoija:** Pi<br>
**Päätös:** **Jatka vain rajattuna pivot-kokeena. Älä jatka nykyistä roadmapia sellaisenaan.**

---

## 1. Johtopäätös

Repo sisältää käyttökelpoisen prototyypin ja hyviä sisältöaihioita. Se ei sisällä vielä tuotetta, jonka kysyntää voisi mitata. Se ei myöskään toteuta dokumentaation lupaamaa autonomista kylää.

Nykyinen järjestelmä tekee kolme asiaa kohtuullisesti:

1. Se tallentaa tapahtumat Postgresiin.
2. Se kuljettaa renderöintityöt Redis-jonon ja LLM-gatewayn kautta.
3. Se sisältää 12 hahmon, 9 paikan ja 73 tapahtumatyypin sisältöpaketin.

Kylän varsinainen autonomia puuttuu. LLM valitsee tällä hetkellä lähinnä `IGNORE`, `POST_FEED`, `POST_CHAT` tai `REPLY`. Se ei liikuta hahmoa, tee kauppaa, lainaa tavaraa, auta, pyydä anteeksi tai muuta maailmaa. Engine syöttää sille valmiiksi kolme arkista tapahtumaa: `LOCATION_VISIT`, `SMALL_TALK` ja `CUSTOMER_INTERACTION`.

Markkina ei ole tyhjä. AI Town, Stanford Generative Agents, DeepMind Concordia, Chirper ja Steamissa julkaistu AI Society kattavat jo suuren osan yleisestä "AI-hahmot elävät keskenään" -ideasta. Koivulahden erottautumistekijäksi ei riitä suomalainen nimi tai paikallinen LLM.

**Jatkaminen kannattaa vain, jos tuote rajataan tähän hypoteesiin:**

> Kuusi muistettavaa suomalaista hahmoa tuottaa seitsemän päivän aikana syy-seuraussuhteiltaan uskottavan live-saippuan, jota katsojat palaavat seuraamaan ja jonka seuraavaan päivään he haluavat vaikuttaa.

Tälle kannattaa antaa neljän viikon, tarkasti rajattu validointijakso. Sen jälkeen Sami joko jatkaa mitatun käytön perusteella tai arkistoi projektin.

### Arvosanat

| Alue | Arvio | Perustelu |
|---|---:|---|
| Konsepti ja sisältöaihio | 7/10 | Suomalainen kylä, mediaformaatit ja hahmocasti muodostavat ymmärrettävän kokonaisuuden. |
| Tekninen perusta | 5/10 | Event-first-ajattelu, Postgres, Redis ja gateway ovat käyttökelpoisia. Toteutus on prototyyppitasoa. |
| Agenttien autonomia | 2/10 | Päätökset koskevat lähes vain julkaisemista. Maailmaa muuttava action loop puuttuu. |
| Sisällön laatu | 4/10 | Rakenne pysyy JSONissa, mutta teksti toistaa fraaseja ja sisältää kielivirheitä. |
| Käyttökokemus | 1/10 | Julkista UI:ta ei ole. API ja CLI-monitori eivät testaa viihdearvoa. |
| Luotettavuus ja replay | 2/10 | Jonot menettävät töitä virheissä. Restart-determinismi epäonnistui 0/5 vertailussa. Replay puuttuu. |
| Tietoturva | 2/10 | Vanha API-avain on remote-branchin tipissä. Palvelut ja tietokannat avataan ilman suojausta. |
| Testaus ja CI | 3/10 | 50 testiä, joista vain 10 toimii ilman käynnissä olevia palveluita. CI puuttuu. |
| Markkinaerottuvuus | 3/10 | Suoria avoimen lähdekoodin, tutkimus- ja kuluttajatuotekilpailijoita on useita. |
| Pelastettavuus | 7/10 | Hahmot, tapahtumakatalogi, event store -ajatus ja osa gatewaysta kannattaa käyttää uudelleen. |

**Nykyinen tuote:** 4/10<br>
**Repo uuden, rajatun vertical slicen lähtöpisteenä:** 7/10

---

## 2. Mitä auditoin

### Repo ja historia

- 70 tracked-tiedostoa, noin 716 kt
- noin 4 953 riviä tuotantokoodia
- noin 546 riviä testikoodia
- 34 committia viideltä aktiiviselta kehityspäivältä
- viimeinen commit 21.12.2025, 206 päivää ennen auditointia
- ei tageja eikä releaseja
- ei lisenssiä
- ei GitHub Actions -workflowta
- nykyinen feature-branch on viisi committia mainia edellä
- paikallinen `main` on kahdeksan committia `origin/main`-branchia edellä
- current feature on yhden tietoturvakommitin `origin/feature/ambient-event-generator`-branchia edellä

Repo syntyi lyhyessä sprintissä. Commit-historia ja `status-and-next.md` näyttävät nopean tutkimusprototyypin, eivät ylläpidetyn tuotteen kehitystä.

### Ajot ja tarkistukset

Auditissa tehtiin seuraavat ajot:

- `compileall`: läpi
- offline-unit-testit: 10/10 läpi
- kuusi omaa Docker-kuvaa: build läpi
- kuusi image-import-smokea: läpi
- `pip check`: läpi kaikissa kuvissa
- `pip-audit`: ei tunnettuja haavoittuvuuksia API- ja decision-service-kuvien nykyisissä, build-hetkellä ratkaistuissa paketeissa
- Ruff: 18 löydöstä
- Bandit: 21 low-löydöstä, ei medium/high-löydöksiä
- eristetty mock-LLM E2E: event -> Redis -> gateway -> post -> API toimi
- repo smoke test eristetyssä E2E:ssä: 3/3 läpi
- oikea Qwen2.5 7B CPU-renderöinti: toimi
- gatewayn contract/quality-testit oikealla Qwenilla: 30 passed, 1 xfailed, 6 xpassed
- restart-determinismivertailu: 0/5 tulevasta routine-eventistä vastasi katkeamatonta ajoa

### E2E-havainto

Nykyisen checkoutin Postgres-init pysähtyi migraatioon `003_ambient_tables.sql`, koska tiedoston käyttöoikeus oli `600` eikä Postgres-kontin käyttäjä pystynyt lukemaan sitä. Auditointi kopioi migraatiot erilliseen testikansioon oikeuksilla `644`. Sen jälkeen perusputki toimi.

Eristetty ajo käytti mock-LLM:ää eikä kutsunut Geminiä. Viiden sekunnin nopeutetussa ajossa syntyi:

- 209 eventtiä
- 56 postausta
- 44 muistia
- 14 relationship-riviä

Määrä kertoo putken toimivan. Se kertoo myös ketjureaktioiden eventtimäärän kasvavan nopeasti.

### Oikea paikallinen malli

Qwen2.5 7B Q4 tuotti CPU-ajossa ensimmäisen vastauksen 28,64 sekunnissa. Testisarja kesti 10 minuuttia 52 sekuntia. Rakenteelliset testit menivät läpi, mutta yksi auditointipostaus oli:

> "Aamulla ensimmäinen pullapelti onnistui! Hyvää alua myyjille!"

Testit hyväksyivät tekstin, vaikka se sisälsi kielivirheen ja oudon loppulauseen. Nykyinen eval mittaa muotoa paremmin kuin viihdearvoa tai suomen laatua.

GPU-profiilia ei saatu tällä koneella käyntiin, koska Dockerilta puuttui NVIDIA Container Toolkit. Koneessa on RTX 3080, mutta `docker run --gpus all` epäonnistui. Tämä on ympäristövika, ei suoraan sovelluskoodin vika.

---

## 3. Nykyinen ratkaisu

### Toteutunut putki

```text
Routine-event / mock ambient / nähty postaus
  -> Engine
  -> Postgres events
  -> Redis decision_jobs
  -> Gemini-päätös
  -> Redis render_jobs
  -> Worker
  -> llama.cpp / Qwen
  -> Postgres posts
  -> FastAPI
  -> ei loppukäyttäjän UI:ta
```

### Käyttökelpoiset osat

#### Event-first-periaate

Engine tallentaa maailman tapahtumat ennen sisällön generointia. Tämä on oikea suunta. LLM ei saa suoraan kirjoittaa maailman totuutta.

#### Sisältöpaketti

Katalogi sisältää:

- 12 NPC-profiilia
- 9 paikkaa
- 73 eventtityyppiä
- tavoitteet, triggerit, salaisuudet ja ääniprofiilit kaikille hahmoille
- Day 1 -skenaarion
- impact scoring -asetukset
- moderointi- ja rate limit -säännöt

Tämä aineisto säästää aikaa uudessa vertical slicessa.

#### Palvelurajat

Engine, päätöksenteko, renderöinti ja API on erotettu käsitteellisesti. Rajat auttavat, vaikka nykyinen kuuden sovelluspalvelun toteutus on liian raskas yhden kehittäjän MVP:lle.

#### Gateway

Gateway lukitsee `channel`, `author_id` ja `source_event_id` requestin arvoihin. Se tukee useita llama.cpp-endpointteja ja JSON-repairia. Adapteriraja kannattaa säilyttää suppeampana versiona.

#### Monitori

`tools/village_monitor.py` auttaa debugissa. Se näyttää eventit, päätökset ja postaukset samassa näkymässä.

---

## 4. Dokumentaation lupaus ja toteutunut tila

| Väite tai ominaisuus | Tila | Auditointihavainto |
|---|---|---|
| Eventit ovat maailman totuus | Toteutuu osin | Engine tallentaa tapahtumat ennen renderöintiä. |
| Jatkuva simulaatio | Toteutuu | Tick-loop ja kolme routine-eventtiä toimivat. |
| 12 autonomista NPC:tä | Ei toteudu | Engine valitsee toiminnan. LLM päättää pääosin julkaiseeko NPC. |
| Action schema | Dataa vain | `MOVE_TO`, `BUY`, `BORROW`, `HELP` ja muut actionit eivät ohjaa runtimea. |
| Tavoiteohjattu toiminta | Ei toteudu | Goalit luetaan päätöspromptiin, mutta ne eivät muuta maailmaa tai päivity. |
| Päivärutiinit | Dataa vain | Kaikilla profiileilla on routine, mutta engine ei käytä sitä. |
| Täysi determinismi | Ei toteudu | Restart-ajo poikkesi 5/5 tulevassa eventissä. LLM-output ei ole seed-deterministinen. |
| Replay | Ei toteudu | Snapshot-taulu ja admin-endpoint ovat stubit. |
| Moderointi | Ei toteudu | Katalogin säännöt eivät vaikuta insertiin tai julkaisuun. |
| Rate limitit | Ei toteudu | Katalogin rajat eivät ole runtimessa. In-memory cooldown kattaa vain fallback-polun. |
| Catalog-promptit käytössä | Ei toteudu | Worker lataa `PROMPT_CONFIG`:in mutta ei käytä sitä. |
| Daily NEWS | Vain Day 1 -seed | Toistuva digest puuttuu. |
| External ambient data | Ei toteudu | Worker käyttää mock-säätä ja mock-uutisia. |
| Post chain reactions | Osittain | DB-kentät ja ensimmäinen vastaustaso toimivat. API ei palauta thread-kenttiä. |
| API channel filter | Ei toteudu | README lupaa filtterin, route hyväksyy vain `limit`-parametrin. |
| Admin start/stop/replay | Stub | Endpointit vastaavat `accepted`, mutta eivät tee toimenpiteitä. |
| Read-only village UI | Puuttuu | Projektin viihdearvoa ei voi testata. |
| Demo-ready | Ei nykytilassa | Quick start kaatuu, Gemini-malli on suljettu ja UI puuttuu. |

---

## 5. Estävät tekniset löydökset

### P0: korjaa ennen seuraavaa normaalia ajoa

#### 5.1 Vanha Gemini-avain on remote-branchin tipissä

Commit `5ef0e06` sisältää kovakoodatun Google API -avaimen. `origin/feature/ambient-event-generator` osoittaa suoraan tähän committiin. Korjauscommit `81a35b5` on vain paikallinen.

Nykyisen `.env`:n avain on eri avain. Vanhan avaimen tila pitää silti tarkistaa, avain pitää perua ja branchin historia pitää siivota tai branch poistaa.

**Toimet:**

1. Peru vanha avain Google Cloudissa.
2. Älä pushaa pelkkää poistocommittia ratkaisuna. Salaisuus jää historiaan.
3. Poista remote-feature-branch tai kirjoita historia uudelleen.
4. Lisää secret scanning CI:hin.

#### 5.2 Oletuspäätösmalli on suljettu

`packages/shared/gemini_client.py:10` käyttää mallia `gemini-2.0-flash-exp`. Google sulki Gemini 2.0 Flash -mallit 1.6.2026. Myös rinnakkainen `gemini-3-flash-preview` on preview-niminen kovakoodaus, eikä runtime käytä sitä.

Nykyinen default-polku ei voi toimia heinäkuussa 2026.

**Toimet:**

- tee provider ja model env-konfiguroitavaksi
- käytä nykyistä GA-mallia
- lisää startupissa capabilities-probe
- estä engineä tuottamasta töitä, jos decision provider ei ole terve

#### 5.3 Quick start kaataa enginen

`.env.example` puuttuu ainakin:

- `DECISION_QUEUE`
- `DECISION_SERVICE_ENABLED`
- `GEMINI_API_KEY`
- ambient-asetukset

Compose syöttää puuttuvan `DECISION_SERVICE_ENABLED`-arvon tyhjänä stringinä. Pydantic kaataa enginen boolean-parsintaan ennen DB-yhteyttä.

#### 5.4 Palvelut avataan hostille ilman suojausta

Compose julkaisee portit 5432, 6379, 8080, 8081 ja 8082 kaikille hostin interfacelle. Redisissä ei ole salasanaa. API:ssa, admin-reiteissä ja LLM-gatewayssa ei ole autentikointia. CORS sallii kaikki originit ja credentialit.

Docker voi ohittaa tavallisia UFW-odotuksia. Tätä composea ei pidä ajaa julkisella palvelimella.

**Toimet:**

- poista Postgresin ja Redisin host-portit
- sido dev-portit `127.0.0.1`:een
- laita API reverse proxyn taakse
- suojaa admin ja gateway autentikoinnilla
- lisää request- ja inference-rate limitit

#### 5.5 Decision-jonon kapasiteetti ei riitä saapuvaan työhön

Engine luo yhden routine-decisionin 10 sekunnissa. Decision-service käsittelee enintään yhden kutsun 10 sekunnissa. Routine-eventit käyttävät siis koko kapasiteetin ennen ambient-eventtejä ja postireaktioita.

Jokainen uusi postaus luo noin puolelle muista NPC:istä uuden päätöstyön. Jono kasvaa ilman ylärajaa. Routine-pohja yksin tarkoittaa 8 640 päätöskutsua päivässä ja arviolta 13-26 miljoonaa input-tokenia päivässä ennen ketjureaktioita.

`DECISION_MIN_INTERVAL` löytyy `.env`:stä, mutta compose ei välitä sitä decision-service-kontille.

### P1: korjaa ennen vertical slice -pilottia

#### 5.6 Redis-listat menettävät töitä

Workerit käyttävät `BRPOP`:ia. Redis poistaa työn ennen generointia tai DB-inserttiä. Prosessin kaatuminen, timeout tai tietokantavirhe hävittää työn. Retrytä, ackia tai dead letter -jonoa ei ole.

Sama puute koskee decision- ja render-jonoa.

#### 5.7 Idempotenssi puuttuu

`posts`-taulussa ei ole unique-rajaa päätökselle, lähde-eventille tai render-jobille. Uudelleenajo voi luoda duplikaatteja. Decision- ja render-jobien ID:t käyttävät satunnaista UUID:ta, mikä rikkoo replayta.

#### 5.8 Restart-determinismi on rikki

Engine yrittää kelata RNG:tä eteenpäin kahdella `choice`-kutsulla per routine-event. Oikea event-generointi käyttää enemmän RNG-kutsuja payloadiin, kohdehahmoon ja paikkavalintaan.

Auditin vertailussa restart-polku vastasi katkeamatonta ajoa 0/5 eventissä.

Determinismi pitää määritellä uudelleen:

- engine on deterministinen annetulla action-logilla ja ambient-snapshotilla
- replay käyttää tallennettuja LLM-päätöksiä
- sama seed yksin ei takaa samaa pilvimallin outputia

#### 5.9 Varsinainen action engine puuttuu

Katalogi lupaa `MOVE_TO`, `TALK_TO`, `BUY`, `SELL`, `BORROW`, `HELP` ja muita toimia. Decision-schema sallii vain julkaisemisen ja ignoren.

Maailmassa ei ole riittävää mutable statea sijainnille, inventaariolle, rahalle, tarpeille tai tehtävien etenemiselle. Hahmojen keskustelu ei voi tuottaa uskottavia seurauksia ilman tätä kerrosta.

#### 5.10 Moderointi ja oikean maailman data eivät kohtaa

Katalogi kieltää oikeisiin ihmisiin ja tapahtumiin kohdistuvan sisällön. Ambient-worker syöttää mockina hallitus-, vaali- ja talousuutisia. Jos mockit vaihdetaan RSS:ään, ulkoinen sisältö menee prompttiin ilman prompt injection -suojausta, lähdepolitiikkaa tai faktantarkistusta.

Poista oikeat uutiset MVP:stä. Sää voidaan generoida simulaation omasta kalenterista.

#### 5.11 Gemini-avain voi vuotaa virhelokiin

Client lisää API-avaimen query stringiin. `httpx.HTTPStatusError` sisältää request-URL:n. `make_decision` tallentaa exception-tekstin `decisions.error`-kenttään. Virhe voi siis kopioida avaimen tietokantaan.

Käytä ylläpidettyä SDK:ta tai header-pohjaista autentikointia. Sanitiseeraa virheet ennen lokitusta.

#### 5.12 Migraatiomalli ei toimi jatkuvassa kehityksessä

Postgres ajaa `/docker-entrypoint-initdb.d`-hakemiston vain tyhjälle volumelle. Uudet migraatiot eivät aja olemassa olevaan kantaan. Repo ei seuraa schema-versiota eikä tarjoa upgrade-komentoa.

Nykyisessä checkoutissa migraatiot 003-005 olivat lisäksi oikeuksilla `600`.

### P2: ylläpidettävyys

- `runner.py` on 1 305 riviä ja se sekoittaa seedauksen, scoringin, ambientin, cooldownit, postijakelun ja tick-loopin.
- `worker.py` on 713 riviä. `make_draft` sisältää noin 159 riviä haarautuvaa template-logiikkaa.
- Kaikki Python-riippuvuudet ratkaistaan buildissa ilman lockfilea.
- Image-tagit eivät käytä digest-pinnejä.
- Kaikki sovelluskontit ajavat root-käyttäjänä.
- Runtime käyttää `assert`-lauseita yhteystilojen tarkistukseen.
- API:n health ei tarkista riippuvuuksia. Gatewayn health ei tarkista LLM-palvelinta.
- `render_jobs`- ja `world_snapshots`-tauluja ei käytetä.
- Post thread -kentät eivät tule API:sta ulos.
- `POST_SEEN` puuttuu event-katalogista.
- Relationship-seedissä on 6 normaalia directed edgeä 132 mahdollisesta, noin 4,5 prosenttia.
- Relationship-arvoja ei rajata välille -100...100.
- Muistien summary on usein vain `EVENT_TYPE @ place`, joten LLM ei saa tapahtuman merkitystä.
- Muistien recency käyttää wall clockia, vaikka simulaatio käyttää sim clockia.
- Ambient `upsert_ambient_event` tulkitsee sekä `INSERT 0 1` että `INSERT 0 0` onnistuneeksi insertiksi.
- Katalogin ilmoitettu event-määrä on 54, todellinen 73.
- Katalogissa on typo `ffection`, kaksi severity-typoa, prompt-template-typoja ja yksi encoding-rikko.
- Meta kertoo "1 sim minute = 2 real seconds", mutta engine etenee suhteessa 1:1.
- Lisenssi on edelleen `TBD`.

---

## 6. Tuote- ja markkina-arvio

### Markkinassa on kiinnostusta

Aihe ei ole kuollut:

- a16z AI Town: 10 164 GitHub-tähteä, aktiivinen 2026
- Stanford Generative Agents: 21 755 tähteä
- DeepMind Concordia: aktiivinen generative social simulation -kirjasto
- Chirper: tutkimusaineistossa yli 65 000 agenttia ja 7,7 miljoonaa AI-postausta
- Showrunner: Amazonin tukema interaktiivisen AI-TV:n hanke
- AI Society: julkaistu Steamissa 20.3.2026

### Geneerinen toteutus ei erotu

Avoimen lähdekoodin starter kit ratkaisee jo virtuaalikylän perusongelman. Tutkimusframeworkit ratkaisevat muistia ja sosiaalista simulaatiota. Kuluttajatuotteet tarjoavat kartan, hahmoeditorin, talouden, suhteet ja pelaajan interventiot.

Koivulahti kilpailee tällä hetkellä lähinnä tekstiputkella. Sillä ei ole UI:ta, kuvia, ääntä, pelimekaniikkaa tai yleisön toimintaa.

### AI Society antaa hyödyllisen varoituksen

AI Society kuvaa lähes samaa lupausta: paikalliset LLM-hahmot työskentelevät, rakentavat suhteita, postaavat someen ja reagoivat pelaajan toimintaan.

Steamissa sillä oli auditointihetkellä 26 arvostelua, joista 16 positiivista ja 10 negatiivista. Arvostelujen toistuvat ongelmat olivat:

- keskustelu ei vaikuta maailmaan
- hahmot sotkevat faktoja
- pelaajan interventiot tuntuvat irrallisilta
- toimintoja ja rakennuksia on liian vähän
- agentit jäävät juttelemaan, koska niillä ei ole tarpeeksi affordansseja
- päätöksenteko on hidasta

Koivulahti kärsii jo kooditasolla samoista ongelmista. Se kannattaa ottaa suunnittelun lähtökohdaksi.

### Suomalaisuus auttaa vain sisältöformaatin kautta

Suomen kieli ja kyläkulttuuri voivat tehdä tuotteesta muistettavan. Ne eivät muodosta teknistä moat-tekijää. Erottuvuus syntyy, jos Sami paketoi simulaation formaatiksi:

- tunnistettavat hahmot
- viikoittaiset kaaret
- lyhyet päivittäiset koosteet
- katsojan äänestys
- syyt ja seuraukset, jotka näkyvät seuraavana päivänä
- vahva visuaalinen identiteetti

Autonomia toimii tuotantotapana. Katsoja ostaa draamaa, huumoria ja vaikutusvaltaa.

### Realistiset käyttötavat

| Suunta | Arvio | Perustelu |
|---|---|---|
| Yleinen AI village -alusta | Älä rakenna | Kilpailu on vahva, eikä nykyinen repo tuo teknistä etua. |
| Itsenäinen kuluttajapeli | Ei vielä | UI, gameplay, animaatio ja retention loop puuttuvat. |
| Seitsemän päivän suomalainen live-saippua | Testaa | Rajattu formaatti käyttää nykyisiä hahmoja ja event-first-ajatusta. |
| IsoRatas-demo / portfolio | Kannattaa | Bounded pilot tuottaa näkyvän agentic-system-casen, vaikka kuluttajatuote ei jatkuisi. |
| Tutkimus- tai benchmark-repo | Mahdollinen | Determinismi, causality-eval ja suomenkielinen sisältö voivat muodostaa oman niche-arvon. |

---

## 7. Suositeltu pivot

### Tuotelupaus

**Koivulahti on seitsemän päivän live-saippua. Kuusi AI-hahmoa elää samassa suomalaisessa kylässä, ja jokainen julkaisu seuraa oikeasta pelimaailman tapahtumasta. Katsojat päättävät kerran päivässä yhden huomisen rajoitteen.**

### Ensimmäinen käyttäjäkysymys

Palaako katsoja huomenna katsomaan, miten eilinen konflikti eteni?

Älä optimoi ensimmäisessä pilotissa agenttien määrää, mallien paikallisuutta tai event-katalogin laajuutta. Mittaa hahmojen muistettavuutta ja tarinan jatkuvuutta.

### Rajaa ensimmäinen kausi

- 6 NPC:tä
- 3 paikkaa
- 8-12 toteutettua eventtityyppiä
- 6 maailmaa muuttavaa actionia
- 2 tarinakaarta
- 7 sim-päivää
- 1 katsojaäänestys päivässä
- FEED, CHAT ja päivän NEWS-kooste
- staattiset hahmopotretit ja vahva mobiili-UI

### Poista pilotista

- oikeat uutisotsikot
- urheilu-API:t
- 12 NPC:n yhtäaikainen päätöslooppi
- fine-tuning
- vector DB
- multi-provider-routing
- julkinen hahmoeditori
- native mobile
- mikropalvelujen lisääminen
- ääni ja video ennen retention-signaalia

---

## 8. Tavoitearkkitehtuuri

### Kolme runtime-osaa riittää

1. **App/API**
   - public UI
   - read API
   - admin ja audience vote

2. **Simulation worker**
   - sim clock
   - legal action generation
   - policy/LLM decision
   - event effects
   - director
   - content jobs

3. **Postgres**
   - run state
   - world state
   - append-only events
   - decisions
   - durable jobs/outbox
   - posts

Redis voidaan jättää pois pilotista. Postgres-job queue `FOR UPDATE SKIP LOCKED` -mallilla riittää tähän volyymiin. Jos Redis säilyy, käytä Streams + consumer groups + ack + dead letter -jonoa.

### Action loop

```text
Havaitse sim clock + paikka + lähellä olevat NPC:t + goals
  -> engine tuottaa vain lailliset action-vaihtoehdot
  -> sääntöpolicy valitsee tavallisen toiminnan
  -> LLM valitsee vain korkean vaikutuksen tilanteissa
  -> engine validoi actionin
  -> engine päivittää statea ja tallentaa eventin
  -> renderer kirjoittaa julkaisun vain valituista eventeistä
```

LLM ei saa keksiä esineitä, rahaa tai tapahtunutta dialogia vapaana tekstinä. Se valitsee legal actionin ja täyttää rajatun payloadin.

### Sisältöputki

Poista englanninkielinen draft ja sanankorvauskäännös. Nykyinen polku tekee ensin englanninkielisen Gemini-draftin, kääntää sanoja substring-replace-logiikalla ja pyytää Qwenia korjaamaan tekstin.

Uusi polku:

- decision output: action, target, intent, emotion, private rationale
- engine event: faktat ja seuraukset
- renderer: yksi suomenkielinen pyyntö eventistä ja hahmon äänestä
- deterministic fallback: laadukas template, ei rikkinäistä LLM-outputia

### Determinismi

Tallenna nämä jokaiseen runiin:

- sim seed
- engine-versio ja config hash
- ambient snapshot
- legal action set
- valittu action
- provider, model ja prompt version
- raw structured decision

Replay käyttää tallennettuja päätöksiä. Uusi run samalla seedillä voi tehdä uuden generatiivisen version, mutta replay ei kutsu mallia.

### Budjetti

Aseta kovat rajat per sim-päivä:

- action-LLM-kutsut, esimerkiksi enintään 30
- render-kutsut, esimerkiksi enintään 25
- FEED per NPC, esimerkiksi enintään 2
- CHAT burst ja thread depth
- token- ja eurobudjetti
- jonon maksimipituus

Engine siirtää vähäarvoiset tapahtumat deterministic policylle tai template-renderöintiin.

---

## 9. Neljän viikon roadmap

### Vaihe 0: turva ja jatkamispäätöksen rajaus, 1-2 päivää

**Tulos:** repo voidaan ajaa turvallisesti ja kaikki tietävät, mitä pilotilla mitataan.

- peru leaked Gemini key
- poista tai rewrite remote-feature-branch
- valitse yksi kanoninen main
- tagaa nykytila `prototype-2025-12`
- tee `.env.example` ajettavaksi
- vaihda supported GA -malliin
- sulje infra-portit
- korjaa migraatiot ja ota Alembic tai yksinkertainen schema version -runner
- lisää `pyproject.toml`, lockfile, Ruff, pytest ja secret scan
- tee GitHub Actions: lint, unit, fake-provider E2E, Docker build

**Gate:** yksi komento käynnistää fake-provider-stackin tyhjästä ja CI menee vihreäksi.

### Vaihe 1: engine vertical slice, 4-5 päivää

**Tulos:** kuusi hahmoa tekee maailmaa muuttavia päätöksiä.

- tee `runs`, `agent_state`, `inventory` ja durable `jobs/outbox`
- persistoi sim clock ja tick
- toteuta 6 actionia: MOVE, TALK, HELP, BORROW, RETURN, APOLOGIZE
- generoi legal action set sääntöjen perusteella
- käytä NPC:n routinea, goalia ja relationshipia valintaan
- rajaa event-katalogi 8-12 runtime-eventtiin
- tee kaksi konfliktikaarta: toripaikka ja peräkärry
- kirjoita replay-testi, jossa event log ja state hash täsmäävät

**Gate:** seitsemän sim-päivän ajo päättyy ilman duplikaatteja, kadonneita jobeja tai mahdottomia actioneita.

### Vaihe 2: sisältö ja eval, 4-5 päivää

**Tulos:** eventit muuttuvat tunnistettavaksi suomeksi ilman toistospämmiä.

- korvaa kaksimallinen English-draft-polku yhdellä rendererillä
- lisää deterministic fallbackit
- tee päivittäinen NEWS-kooste
- tee muistot tapahtuman faktoista ja seurauksesta
- tee eval-setti 50 tilanteelle
- mittaa personaerottuvuus, faktat, toisto, syy-seuraus, turvallisuus ja kieli
- tee human review -näkymä hyväksy/hylkää/korjaa

**Gate:** vähintään 80 % human review -näytteistä saa arvosanan 4/5 faktatarkkuudessa ja hahmon äänessä. Vakavia ristiriitoja alle 5 %.

### Vaihe 3: katsojan vertical slice, 4-5 päivää

**Tulos:** ulkopuolinen käyttäjä voi seurata kylää puhelimella.

- mobiili-first FEED, CHAT ja NEWS
- hahmoprofiilit ja suhteet
- "Aiemmin Koivulahdessa" -kooste
- threadit
- päivän yleisöäänestys
- kevyt admin: pause, inject opportunity, reject post
- analytics: session, return, character view, vote

**Gate:** viisi ulkopuolista testikäyttäjää ymmärtää ilman ohjeita, kuka riitelee, miksi ja mitä he voivat tehdä.

### Vaihe 4: seitsemän päivän suljettu kausi, 7 päivää

**Tulos:** oikea jatka/lopeta-päätös.

- kutsu 20-50 testaajaa
- julkaise yksi uusi sim-päivä päivässä
- pidä kustannuskatto
- kerää retention, vote rate ja lyhyt käyttäjähaastattelu
- älä korjaa tarinaa käsin muuten kuin safety/editorial vetoilla

**Jatka, jos:**

- vähintään 20 oikeaa testaajaa aloittaa
- vähintään 40 % palaa kolmantena päivänä
- vähintään 30 % osallistuu vähintään yhteen äänestykseen
- vähintään 60 % osaa nimetä yhden hahmon ja keskeneräisen konfliktin
- vähintään 50 % sanoo haluavansa toisen kauden
- kustannus pysyy asetetussa päiväbudjetissa

**Arkistoi tai muuta formaattia, jos:**

- D3-retention jää alle 25 % kahden sisältöiteraation jälkeen
- käyttäjät kuvaavat kokemusta "AI:t juttelevat keskenään" eivätkä muista hahmoja
- konfliktien seuraukset vaativat jatkuvaa käsikirjoittajan korjausta
- viihdearvo syntyy vain noveltystä

---

## 10. Työmäärä ja uudelleenkäyttö

### Käytä uudelleen

- 12 NPC-profiilia, joista valitaan 6
- paikat
- event-first-periaate
- event-, post- ja relationship-skeemojen idea
- osa impact scoringista
- gatewayn request-lockit
- monitorin käyttöliittymäideat
- Day 1 -kaaret sisältöaihioina

### Kirjoita uudelleen tai pura

- `runner.py` vastuualueisiin
- decision-schema
- durable job pipeline
- sim clock ja replay
- workerin English draft + keyword translation
- migration handling
- API:n admin-stubit
- CORS ja verkotus
- testit

Arviolta 30-40 prosenttia nykyisestä koodista kannattaa käyttää sellaisenaan tai pienin muutoksin. Sisältödatasta voi käyttää enemmän. Repoa ei tarvitse heittää pois, mutta core-loopin paikkaaminen nykyisen 1 305-rivisen runnerin sisään kasvattaa velkaa nopeasti.

---

## 11. Priorisoitu tehtävälista

### P0, ennen seuraavaa normaalia ajoa

1. Revoke vanha leaked Gemini key.
2. Siivoa remote-branch ja valitse kanoninen main.
3. Vaihda suljettu Gemini-malli nykyiseen GA-malliin.
4. Korjaa `.env.example`.
5. Sulje Postgres, Redis, llama.cpp ja gateway Docker-verkon sisään.
6. Korjaa migraatioiden oikeudet ja versionointi.
7. Laita decision-service oletuksena pois, kunnes kapasiteetti ja provider health on korjattu.

### P1, ensimmäinen rakennusviikko

1. Lisää fake-provider E2E CI:hin.
2. Tee durable jobs ja idempotency keys.
3. Persistoi run, sim clock ja config hash.
4. Tee kuuden actionin legal action loop.
5. Poista oikeat uutiset pilotista.
6. Rajaa casti kuuteen hahmoon.

### P2, ennen käyttäjäpilottia

1. Tee mobile UI.
2. Lisää daily digest ja audience vote.
3. Tee human-rated eval.
4. Lisää moderointi ja editorial veto.
5. Instrumentoi retention ja kustannus.

---

## 12. Päätös vaihtoehdoittain

### Vaihtoehto A: jatka nykyistä roadmapia

**Päätös: ei.** Se lisää digestin, ambient-API:t, muistitiivistykset ja lisää eventtejä ennen kuin core autonomy tai käyttäjäkokemus toimii.

### Vaihtoehto B: täydellinen rewrite

**Päätös: ei heti.** Sisältödata ja event-first-ajattelu ovat arvokkaita. Tee ensin pieni vertical slice nykyiseen repoon selkeillä uusilla moduleilla. Älä jatka vanhan runnerin kasvattamista.

### Vaihtoehto C: neljän viikon pivot-pilotti

**Päätös: kyllä.** Tämä on suositus. Bounded kokeilu voi tuottaa joko toimivan formaatin tai halvan lopetuspäätöksen.

### Vaihtoehto D: arkistoi nyt

**Päätös: perusteltu, jos tavoitteena oli yleinen AI village -alusta tai nopea kuluttajabisnes.** Kilpailu ja puuttuva UI tekevät siitä huonon sijoituksen. IsoRatas-demo ja suomalainen live-saippua antavat kuitenkin yhdelle rajatulle pilotille riittävän syyn.

---

## 13. Lähteet

Tarkistettu 16.7.2026.

1. Google Gemini 2.0 Flash shutdown: https://ai.google.dev/gemini-api/docs/models/gemini-2.0-flash
2. a16z AI Town: https://github.com/a16z-infra/ai-town
3. Stanford Generative Agents: https://github.com/joonspk-research/generative_agents
4. Google DeepMind Concordia: https://github.com/google-deepmind/concordia
5. Project Sid: https://arxiv.org/abs/2411.00114
6. Chirper.ai research: https://arxiv.org/abs/2504.10286
7. AI Society on Steam: https://store.steampowered.com/app/4468180/AI_Society/
8. Showrunner launch coverage: https://www.forbes.com/sites/charliefink/2025/07/30/amazon-backs-showrunners-ai-streaming-platform-as-it-launches-satirical-series-exit-valley/

GitHub-tähtimäärät ja Steam-arvostelujen määrät ovat auditointipäivän snapshotteja, eivät kysyntäennusteita.

---

## Lopullinen suositus

**Pidä repo. Jäädytä nykyinen roadmap. Korjaa P0-asiat ja rakenna neljän viikon live-saippua-pilotti.**

Jos käyttäjät palaavat hahmojen ja keskeneräisten konfliktien takia, projekti ansaitsee toisen kauden. Jos he palaavat vain katsomaan AI-demonstratiota kerran, arkistoi kuluttajatuote ja julkaise työ IsoRatas-case studyna.
