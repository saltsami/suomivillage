-- Migration 004: Post Chain Reactions
-- Adds support for reply chains and post visibility tracking

-- Add reply support to posts
ALTER TABLE posts ADD COLUMN IF NOT EXISTS parent_post_id BIGINT REFERENCES posts(id);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS reply_type TEXT;  -- question/agree/disagree/joke/worry/NULL

-- Index for finding replies to a post
CREATE INDEX IF NOT EXISTS idx_posts_parent ON posts(parent_post_id) WHERE parent_post_id IS NOT NULL;

-- Track which NPCs have seen which posts (for deterministic delivery)
CREATE TABLE IF NOT EXISTS post_deliveries (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    npc_id TEXT NOT NULL,
    seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    replied BOOLEAN DEFAULT FALSE,
    UNIQUE(post_id, npc_id)
);

CREATE INDEX IF NOT EXISTS idx_post_deliveries_post ON post_deliveries(post_id);
CREATE INDEX IF NOT EXISTS idx_post_deliveries_npc ON post_deliveries(npc_id);
CREATE INDEX IF NOT EXISTS idx_post_deliveries_unreplied ON post_deliveries(post_id, npc_id) WHERE NOT replied;

-- Comment for documentation
COMMENT ON TABLE post_deliveries IS 'Tracks NPC visibility of posts for chain reactions';
COMMENT ON COLUMN posts.parent_post_id IS 'References parent post for replies';
COMMENT ON COLUMN posts.reply_type IS 'Type of reply: question, agree, disagree, joke, worry';
