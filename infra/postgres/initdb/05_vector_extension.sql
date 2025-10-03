-- lumen/infra/postgres/initdb/05_vector_extension.sql
-- Enable pgvector extension for embedding similarity search

-- Install pgvector extension (requires superuser)
CREATE EXTENSION IF NOT EXISTS vector;

COMMENT ON EXTENSION vector IS 'Vector similarity search for embeddings';

-- Grant usage to all schemas
-- This allows member schemas to use vector types
ALTER DATABASE lumen SET search_path TO public, control;

-- Note: You may need to install pgvector in your Docker image
-- Add this to your Dockerfile:
-- RUN apt-get update && apt-get install -y postgresql-15-pgvector