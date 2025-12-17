# POST_SEEN Chain Reactions Spec

## Tavoite

Kun NPC postaa (esim. sääreaktio), muut NPC:t voivat nähdä ja reagoida siihen → luontevat someketjut.

## Event-tyypit

### POST_PUBLISHED
Syntyy kun post tallennetaan tietokantaan.

```json
{
  "id": "evt_post_published_123",
  "type": "POST_PUBLISHED",
  "ts_local": "2025-12-17T10:00:00Z",
  "actors": ["npc_kaisa"],
  "payload": {
    "post_id": 123,
    "channel": "FEED",
    "text": "Lunta sataa! Kuka lähtee pulkkamäkeen?",
    "trigger_event_id": "evt_ambient_seen_...",  // alkuperäinen ärsyke
    "author_archetype": "social"
  }
}
```

### POST_SEEN
Syntyy kun NPC "näkee" postin (deterministinen jakelu).

```json
{
  "id": "evt_post_seen_123_npc_aila",
  "type": "POST_SEEN",
  "ts_local": "2025-12-17T10:01:00Z",
  "actors": ["npc_aila"],
  "payload": {
    "post_id": 123,
    "author_id": "npc_kaisa",
    "channel": "FEED",
    "text": "Lunta sataa! Kuka lähtee pulkkamäkeen?",
    "viewer_archetype": "gossip",
    "relationship": "friend"  // friend/neutral/enemy
  }
}
```

### POST_REPLIED
Syntyy kun NPC päättää vastata.

```json
{
  "id": "evt_post_replied_123_npc_aila",
  "type": "POST_REPLIED",
  "ts_local": "2025-12-17T10:02:00Z",
  "actors": ["npc_aila"],
  "payload": {
    "post_id": 123,
    "parent_post_id": 123,
    "reply_type": "question",  // question/agree/disagree/joke/worry
    "draft": "Kuka lähtee? Kuulin että Petrikin miettii..."
  }
}
```

## Jakelumalli (Deterministinen)

### Visibility-funktio

```python
def should_see_post(post_id: str, npc_id: str, author_id: str, channel: str) -> float:
    """Returns visibility probability 0.0-1.0"""
    base = 0.3  # 30% baseline

    # Relationship bonus
    rel = get_relationship(npc_id, author_id)
    if rel == "friend": base += 0.4
    elif rel == "enemy": base += 0.2  # enemies watch each other

    # Channel modifier
    if channel == "CHAT": base += 0.2  # CHAT on kohdennetumpi

    # Archetype modifier
    arch = get_archetype(npc_id)
    if arch in ["gossip", "social"]: base += 0.2
    elif arch == "stoic": base -= 0.2

    # Deterministic: hash(post_id + npc_id) % 100 < base * 100
    return min(1.0, base)
```

### Delivery-prosessi

1. Worker tallentaa postin → emit POST_PUBLISHED
2. Engine kuuntelee POST_PUBLISHED (tai pollaa uudet postit)
3. Jokaiselle NPC:lle (paitsi author):
   - Laske visibility-probability
   - Hash-tarkistus: `hash(post_id:npc_id) % 100 < prob * 100`
   - Jos näkee → emit POST_SEEN
4. POST_SEEN käsittely → mahdollinen POST_REPLIED

## Reply-heuristiikka (Archetype-pohjainen)

**Ei LLM:ää päätöksenteossa** - vain tekstin muotoilussa.

| Archetype | Reply todennäköisyys | Reply-tyyppi |
|-----------|---------------------|--------------|
| gossip | 60% | Kysyy lisätietoa, levittää |
| social | 50% | Kutsuu mukaan, heittää läppää |
| political | 40% | Valittaa, syyttää, ehdottaa |
| anxious | 35% | Huolestuu, varoittelee |
| romantic | 30% | Komppaa, fiilistelee |
| practical | 20% | Ratkaisukeskeinen kommentti |
| stoic | 5% | Harvoin vastaa |

### Reply-draft generaattori

```python
REPLY_TEMPLATES = {
    "gossip": {
        "question": ["Kuulin kanssa... Tiedätkö lisää?", "Mitäs muut on mieltä?"],
        "spread": ["Joo tämähän on juttu! Pitää kertoa..."],
    },
    "social": {
        "invite": ["Mäkin tuun! Ketä muita?", "Lähtisitkö kahville?"],
        "joke": ["Haha, klassikko!", "No jopas!"],
    },
    "political": {
        "blame": ["Tämäkin on kunnan vika.", "Taas sama meno."],
        "solution": ["Pitäisi tehdä jotain.", "Meidän pitäis puhua tästä."],
    },
    "anxious": {
        "worry": ["Toivottavasti ei käy huonosti...", "Olkaa varovaisia!"],
    },
    "romantic": {
        "agree": ["Niin kaunista!", "Täysin samaa mieltä."],
    },
    "practical": {
        "solution": ["Kannattaa varautua.", "Näin se menee."],
    },
}
```

## Tietokantamuutokset

### posts-taulu (lisäykset)

```sql
ALTER TABLE posts ADD COLUMN parent_post_id BIGINT REFERENCES posts(id);
ALTER TABLE posts ADD COLUMN reply_type TEXT;  -- question/agree/disagree/joke/worry
```

### post_deliveries-taulu (uusi)

```sql
CREATE TABLE post_deliveries (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    npc_id TEXT NOT NULL,
    seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    replied BOOLEAN DEFAULT FALSE,
    UNIQUE(post_id, npc_id)
);

CREATE INDEX idx_post_deliveries_post ON post_deliveries(post_id);
CREATE INDEX idx_post_deliveries_npc ON post_deliveries(npc_id);
```

## Cooldown-säännöt

- NPC ei voi vastata samaan postiin kahdesti
- NPC ei voi vastata omaan postiin
- Sama NPC+channel cooldown pätee (CHAT 30min, FEED 2h)
- Max 3 reply-leveliä (ei infinite chains)

## Milestone-kriteerit

✅ Valmis kun:
1. Yhdestä AMBIENT_WEATHER snow eventistä syntyy 1-3 FEED-postausta
2. Vähintään 1 niistä laukaisee POST_SEEN
3. Vähintään 1 reply syntyy
4. Reply tulee oikealta archetype-linjalta:
   - gossip kysyy
   - political valittaa
   - social kutsuu

## Toteutusjärjestys

1. ✅ Migraatio: `posts.parent_post_id`, `posts.reply_type`, `post_deliveries`
2. Engine: `distribute_post_visibility()` - jakelu kuten ambient
3. Engine: `should_reply()` - archetype-pohjainen päätös
4. Engine: `generate_reply_draft()` - template-pohjainen draft
5. Worker: Render reply samalla tavalla kuin muutkin postit
6. Testit: Varmista ketjun syntyminen
