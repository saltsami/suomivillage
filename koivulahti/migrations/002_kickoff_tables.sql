CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL, -- npc|place|item
  name TEXT NOT NULL,
  meta JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS npc_profiles (
  npc_id TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
  profile JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS relationships (
  from_npc TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  to_npc TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  mode TEXT,
  trust INT NOT NULL DEFAULT 0,
  respect INT NOT NULL DEFAULT 0,
  affection INT NOT NULL DEFAULT 0,
  jealousy INT NOT NULL DEFAULT 0,
  fear INT NOT NULL DEFAULT 0,
  grievances JSONB NOT NULL DEFAULT '[]'::jsonb,
  debts JSONB NOT NULL DEFAULT '[]'::jsonb,
  last_interaction_ts TIMESTAMPTZ,
  PRIMARY KEY (from_npc, to_npc)
);

CREATE TABLE IF NOT EXISTS memories (
  id BIGSERIAL PRIMARY KEY,
  npc_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  importance REAL NOT NULL DEFAULT 0.1,
  summary TEXT,
  embedding JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS goals (
  id BIGSERIAL PRIMARY KEY,
  npc_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  horizon TEXT NOT NULL,   -- short|long
  priority REAL NOT NULL DEFAULT 0.5,
  goal_json JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'active', -- active|done|failed|paused
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_relationships_from ON relationships(from_npc);
CREATE INDEX IF NOT EXISTS idx_relationships_to ON relationships(to_npc);
CREATE INDEX IF NOT EXISTS idx_memories_npc_created ON memories(npc_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_goals_npc_status ON goals(npc_id, status);
