CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chat_history (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_history_session ON chat_history (session_id, created_at);

CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(768),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- ivfflat needs data to be useful; harmless when empty.
CREATE INDEX IF NOT EXISTS idx_documents_embedding
    ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Global knowledge base. Mirrors backend/sql/migrations/002_knowledge_facts.sql,
-- which is what an already-created volume must apply by hand.
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

-- Read-only role for the SQL agent tool. This is the real SEC-001 boundary;
-- the query validator in sql_tool.py is only the second layer.
-- The password arrives as a psql variable from 01-init.sh, which reads it from
-- the environment. Never write a credential into a file tracked by Git.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rag_readonly') THEN
        EXECUTE format('CREATE ROLE rag_readonly LOGIN PASSWORD %L', :'ro_password');
    END IF;
END $$;

-- Aggregated view instead of the raw table: the agent can still answer
-- "how many chats today" without being able to read anyone's messages.
CREATE OR REPLACE VIEW chat_stats AS
SELECT session_id,
       role,
       date_trunc('day', created_at) AS day,
       count(*)                      AS message_count,
       min(created_at)               AS first_at,
       max(created_at)               AS last_at
FROM chat_history
GROUP BY session_id, role, date_trunc('day', created_at);

REVOKE ALL ON SCHEMA public FROM rag_readonly;
GRANT CONNECT ON DATABASE agentic_rag TO rag_readonly;
GRANT USAGE ON SCHEMA public TO rag_readonly;
-- documents.content is the RAG corpus (already exposed via rag_search);
-- chat_history is NOT granted - only its aggregate view.
GRANT SELECT ON documents, chat_stats TO rag_readonly;
