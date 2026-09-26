-- Global knowledge base: facts learned from conversation, reusable in every
-- session. init.sql only runs when the Docker volume is created, so an already
-- running database needs this file applied by hand:
--
--   docker exec -i agentic-rag-ai-db psql -U postgres -d agentic_rag \
--     < backend/sql/migrations/002_knowledge_facts.sql
--
-- Idempotent: safe to run more than once.

CREATE TABLE IF NOT EXISTS knowledge_facts (
    id BIGSERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding VECTOR(768),
    -- Only 'approved' rows are ever searched. The agent may create 'pending'
    -- rows; with no auth, letting it publish directly would mean one hostile
    -- prompt in one session poisons every other session, permanently.
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    origin VARCHAR(20) NOT NULL DEFAULT 'agent',
    source_session_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    CONSTRAINT knowledge_facts_status_check
        CHECK (status IN ('pending', 'approved', 'rejected')),
    CONSTRAINT knowledge_facts_origin_check
        CHECK (origin IN ('agent', 'human'))
);

-- No ivfflat index here, deliberately. It is an approximate index: with one
-- probe over 100 lists it returns nothing at all until the table holds
-- thousands of rows, which was reproduced here - an approved fact was simply
-- invisible to the search. The fact table is small (hundreds of short rows),
-- so an exact scan is both correct and fast. Add an index only with a measured
-- row count and `SET ivfflat.probes`.
CREATE INDEX IF NOT EXISTS idx_knowledge_facts_status
    ON knowledge_facts (status, created_at DESC);

-- One proposal per distinct text, case- and whitespace-insensitive: the agent
-- will otherwise re-propose the same fact in every session that mentions it.
CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_facts_content
    ON knowledge_facts (lower(content));

-- Deliberately NOT granted to rag_readonly: the sql_query tool must not be able
-- to read proposals that no human has approved.
REVOKE ALL ON knowledge_facts FROM rag_readonly;
