CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  sim_ts TIMESTAMPTZ NOT NULL,
  place_id TEXT,
  type TEXT NOT NULL,
  actors JSONB NOT NULL,
  targets JSONB NOT NULL,
  publicness REAL NOT NULL,
  severity REAL NOT NULL,
  payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS world_snapshots (
  id BIGSERIAL PRIMARY KEY,
  sim_ts TIMESTAMPTZ NOT NULL,
  state JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS render_jobs (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  status TEXT NOT NULL DEFAULT 'queued',  -- queued|processing|done|failed
  channel TEXT NOT NULL,                  -- FEED|CHAT|NEWS
  author_id TEXT NOT NULL,
  source_event_id TEXT NOT NULL,
  prompt_context JSONB NOT NULL,
  result JSONB,
  error TEXT
);

CREATE TABLE IF NOT EXISTS posts (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  channel TEXT NOT NULL,
  author_id TEXT NOT NULL,
  source_event_id TEXT NOT NULL,
  tone TEXT NOT NULL,
  text TEXT NOT NULL,
  tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  safety_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_posts_channel_created ON posts(channel, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_sim_ts ON events(sim_ts);

