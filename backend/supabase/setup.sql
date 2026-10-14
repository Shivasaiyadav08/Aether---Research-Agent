-- Run once in Supabase SQL Editor before starting Crebry. Additive only.
-- Private backend schema: do NOT add crebry to the Data API exposed schemas.
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
CREATE SCHEMA IF NOT EXISTS crebry;
REVOKE ALL ON SCHEMA crebry FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA crebry FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA crebry REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;
SET search_path = crebry, extensions, public;

CREATE TABLE IF NOT EXISTS crebry.document_chunks (
    workspace_id varchar(200) NOT NULL,
    document_id varchar(200) NOT NULL,
    version varchar(200) NOT NULL,
    chunk integer NOT NULL,
    name varchar(240) NOT NULL,
    page integer NOT NULL,
    content text NOT NULL,
    embedding vector(768) NOT NULL,
    PRIMARY KEY (workspace_id, document_id, version, chunk)
);
ALTER TABLE crebry.document_chunks ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON crebry.document_chunks FROM PUBLIC, anon, authenticated;

-- Private uploads. An existing bucket is left unchanged; startup rejects a public bucket.
INSERT INTO storage.buckets (id, name, public, file_size_limit)
VALUES ('crebry-documents', 'crebry-documents', false, 10485760)
ON CONFLICT (id) DO NOTHING;
