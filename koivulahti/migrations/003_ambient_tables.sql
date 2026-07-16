-- Migration 003: Ambient Event Generator Tables
-- Enables external stimuli (weather, news) to trigger NPC reactions

-- Raw API responses stored for replay determinism
CREATE TABLE IF NOT EXISTS ambient_sources (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  provider TEXT NOT NULL,            -- "weather", "news", "sports"
  region TEXT,
  request JSONB NOT NULL,            -- API request params
  response JSONB NOT NULL            -- raw JSON / parsed feed items
);

-- Normalized ambient events ready for distribution
CREATE TABLE IF NOT EXISTS ambient_events (
  id TEXT PRIMARY KEY,               -- stable id, e.g. amb_20251216_weather_001
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sim_date DATE NOT NULL,
  type TEXT NOT NULL,                -- AMBIENT_WEATHER / AMBIENT_NEWS_HEADLINE / ...
  region TEXT,
  topic TEXT NOT NULL,               -- weather_snow, news_suomi, sports_hockey...
  intensity REAL NOT NULL,           -- 0..1 how significant
  sentiment REAL NOT NULL,           -- -1..1 negative to positive
  confidence REAL NOT NULL,          -- 0..1 how reliable
  expires_at TIMESTAMPTZ,            -- when this event is no longer relevant
  source_ref JSONB NOT NULL,         -- {provider, ambient_source_id, raw_id}
  payload JSONB NOT NULL             -- {summary_fi, facts[], headline?, link?}
);

-- Tracks which NPCs have been delivered which ambient events (prevents re-delivery)
CREATE TABLE IF NOT EXISTS ambient_deliveries (
  id BIGSERIAL PRIMARY KEY,
  ambient_event_id TEXT NOT NULL REFERENCES ambient_events(id) ON DELETE CASCADE,
  npc_id TEXT NOT NULL,
  delivered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (ambient_event_id, npc_id)
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_ambient_sources_provider ON ambient_sources(provider);
CREATE INDEX IF NOT EXISTS idx_ambient_sources_created ON ambient_sources(created_at);
CREATE INDEX IF NOT EXISTS idx_ambient_events_sim_date ON ambient_events(sim_date);
CREATE INDEX IF NOT EXISTS idx_ambient_events_type ON ambient_events(type);
CREATE INDEX IF NOT EXISTS idx_ambient_events_expires ON ambient_events(expires_at);
CREATE INDEX IF NOT EXISTS idx_ambient_deliveries_npc ON ambient_deliveries(npc_id);
CREATE INDEX IF NOT EXISTS idx_ambient_deliveries_event ON ambient_deliveries(ambient_event_id);
