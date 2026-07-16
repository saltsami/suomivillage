-- Migration 005: Decision Service tables
-- Tracks NPC decisions made by the Decision LLM

CREATE TABLE IF NOT EXISTS decisions (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT UNIQUE NOT NULL,
    npc_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    stimulus_event_id TEXT REFERENCES events(id) ON DELETE SET NULL,
    stimulus_type TEXT NOT NULL,  -- AMBIENT_SEEN, POST_SEEN, ROUTINE, etc.
    context_snapshot JSONB NOT NULL,  -- Full context used for decision
    llm_input JSONB NOT NULL,  -- Prompt sent to LLM
    llm_output JSONB NOT NULL,  -- Raw LLM response
    action TEXT NOT NULL,  -- IGNORE, POST_FEED, POST_CHAT, REPLY
    intent TEXT,  -- spread_info, agree, disagree, joke, worry, practical, emotional
    emotion TEXT,  -- curious, happy, annoyed, worried, neutral, amused
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    latency_ms INT,
    llm_provider TEXT DEFAULT 'gemini',
    error TEXT  -- If decision failed
);

-- Indexes for common queries
CREATE INDEX idx_decisions_npc ON decisions(npc_id);
CREATE INDEX idx_decisions_action ON decisions(action);
CREATE INDEX idx_decisions_processed ON decisions(processed_at DESC);
CREATE INDEX idx_decisions_stimulus ON decisions(stimulus_event_id) WHERE stimulus_event_id IS NOT NULL;

-- Add queue name setting
COMMENT ON TABLE decisions IS 'Audit log of all NPC decisions made by the Decision Service';
