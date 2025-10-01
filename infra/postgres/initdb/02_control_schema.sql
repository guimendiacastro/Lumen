-- lumen/infra/postgres/initdb/02_control_schema.sql
-- Global control schema (lives inside the same DB for dev; in prod you can split if you want)

CREATE SCHEMA IF NOT EXISTS control;

-- Members (one per organization / workspace)
CREATE TABLE IF NOT EXISTS control.members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id TEXT UNIQUE NOT NULL,           -- Maps to Clerk Organization ID (later)
  name TEXT NOT NULL,
  specialization TEXT NOT NULL,
  schema_name TEXT NOT NULL UNIQUE,      -- e.g. mem_01, mem_02 ...
  vault_key_id TEXT NOT NULL,            -- e.g. transit/keys/mem_01
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Users (Clerk users that belong to an org)
CREATE TABLE IF NOT EXISTS control.users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clerk_user_id TEXT UNIQUE NOT NULL,
  org_id TEXT NOT NULL,                  -- Foreign to members.org_id (logical)
  role TEXT NOT NULL,                    -- admin | lawyer | support
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON SCHEMA control IS 'Global mapping for LUMEN tenants and users (no private client data here).';
COMMENT ON TABLE control.members IS 'Maps external org (Clerk) to an internal workspace schema and its Vault key.';
