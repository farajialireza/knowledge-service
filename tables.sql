CREATE SCHEMA IF NOT EXISTS ai_assistant;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE ai_assistant.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size BIGINT NOT NULL,
    file_hash CHAR(64) NOT NULL,
    content_hash CHAR(64),
    status VARCHAR(20) NOT NULL DEFAULT 'processing'
        CHECK (status IN ('processing', 'active', 'inactive', 'failed')),
    last_used_at TIMESTAMPTZ,
    usage_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX documents_file_hash_idx
ON ai_assistant.documents (file_hash);

CREATE INDEX documents_content_hash_idx
ON ai_assistant.documents (content_hash);

CREATE INDEX documents_status_idx
ON ai_assistant.documents (status);

---

CREATE TABLE ai_assistant.document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL
        REFERENCES ai_assistant.documents(id)
        ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    context TEXT,
    embedding VECTOR(1536) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (document_id, chunk_index)
);

CREATE INDEX document_chunks_embedding_idx
ON ai_assistant.document_chunks
USING hnsw (embedding vector_cosine_ops);

---

CREATE TABLE ai_assistant.ingestion_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL
        REFERENCES ai_assistant.documents(id)
        ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    error_code TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ingestion_jobs_document_id_idx
ON ai_assistant.ingestion_jobs (document_id);

CREATE INDEX ingestion_jobs_status_idx
ON ai_assistant.ingestion_jobs (status);

---

CREATE EXTENSION IF NOT EXISTS pgcrypto;