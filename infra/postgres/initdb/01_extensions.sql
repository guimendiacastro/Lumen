-- lumen/infra/postgres/initdb/01_extensions.sql
-- Runs automatically on first container startup against the ${POSTGRES_DB} database.

-- Needed for gen_random_uuid() and other crypto helpers
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- Optional, some teams prefer uuid_generate_v4(); either is fine
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
