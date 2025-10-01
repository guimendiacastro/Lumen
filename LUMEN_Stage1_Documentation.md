# LUMEN -- Stage 1 Development Documentation

This document is a **personal reference** summarizing everything that
has been built so far for Stage 1 of the LUMEN project, including
infrastructure, database schema, API endpoints, and front‑end setup.

------------------------------------------------------------------------

## 1. Overall Architecture

LUMEN is a **multi‑tenant, secure AI orchestration platform** for
lawyers.\
Stage 1 focuses on: - Setting up isolated schemas per member (tenant
isolation). - Secure data encryption with HashiCorp Vault Transit. - A
backend API in FastAPI that can: - Manage documents and version
history. - Manage chat threads and messages. - Fan‑out AI queries to
GPT‑4, Claude, and Grok in parallel. - Allow the user to choose an AI
answer, apply it to a document, and version the change. - A front‑end
(Vite + React + Clerk + Monaco) that allows: - Secure login. - Chat
interface with history. - Side‑by‑side AI answers. - Monaco‑based
editable document view. - Selecting and applying an answer to the
document.

------------------------------------------------------------------------

## 2. Technologies Used

  ---------------------------------------------------------------------------------
  Layer                    Tech / Tool                        Purpose
  ------------------------ ---------------------------------- ---------------------
  **Database**             PostgreSQL 15 (Docker)             Multi‑tenant DB with
                                                              per‑member schema
                                                              isolation

  **Secrets / Crypto**     HashiCorp Vault (Transit Engine)   Envelope encryption
                                                              of document content,
                                                              chat messages, AI
                                                              responses

  **Backend**              FastAPI + SQLAlchemy (async)       REST API server with
                                                              tenant isolation via
                                                              `search_path`

  **Auth (dev)**           Dev fake identity (real stage will Map user/org to
                           use Clerk JWTs)                    schema & Vault key

  **LLM Providers**        OpenAI (GPT‑4o‑mini), Anthropic    Parallel responses
                           (Claude 3.5 Sonnet), xAI (Grok 2)  

  **Front‑end**            Vite + React + TypeScript + Clerk  Web UI

  **Editor**               Monaco Editor                      Editable legal
                                                              document

  **State Mgmt**           Zustand                            Store
                                                              doc/thread/messages
                                                              in React

  **Container Mgmt**       Docker Compose                     Run Postgres + Vault
                                                              locally
  ---------------------------------------------------------------------------------

------------------------------------------------------------------------

## 3. Database Schema

### 3.1 Control Schema

Shared `control` schema stores which organization maps to which schema
and Vault key:

``` sql
CREATE TABLE control.members (
  org_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  specialization TEXT,
  schema_name TEXT NOT NULL,
  vault_key_id TEXT NOT NULL
);
```

Sample data:

``` sql
INSERT INTO control.members (org_id, name, specialization, schema_name, vault_key_id)
VALUES ('org_dev_01', 'Dev Member', 'M&A', 'mem_01', 'transit/keys/dev_member');
```

### 3.2 Member Schema (`mem_01`)

Each member has a dedicated schema with:

-   **documents** -- stores encrypted document content.
-   **doc_versions** -- stores historical versions of documents.
-   **chat_threads** -- represents conversations linked to a document.
-   **chat_messages** -- stores user/assistant messages, sanitized +
    encrypted.
-   **ai_requests** -- logs each fan‑out request.
-   **ai_responses** -- encrypted provider responses.
-   **ai_selections** -- records which answer the user chose and
    metadata.
-   **audit_logs** -- immutable log of actions.

Encrypted fields use Vault Transit with per‑member keys.

------------------------------------------------------------------------

## 4. API Endpoints

### 4.1 Bootstrap

-   `POST /bootstrap/member-schema` → create schema/tables if not
    exists.

### 4.2 Documents

-   `POST /documents` → create new encrypted doc.
-   `GET /documents/{id}` → fetch + decrypt.
-   `PUT /documents/{id}` → update + re‑encrypt content.

### 4.3 Threads & Messages

-   `POST /threads` → create thread linked to document.
-   `POST /threads/{id}/messages` → add user message (encrypted &
    sanitized).
-   `GET /threads/{id}/messages` → list sanitized messages (for
    debugging).

### 4.4 AI Orchestration

-   `POST /ai/compare` →
    -   Rebuilds entire chat history (sanitized).
    -   Fan‑outs request to GPT‑4, Claude, Grok in parallel.
    -   Stores encrypted responses and returns plain text to client.
-   `POST /ai/selection` →
    -   Stores chosen AI answer as an assistant message (conversation
        memory).
    -   Applies text to document (append/replace/insert).
    -   Creates version in `doc_versions`.
    -   Writes `ai_selections` and `audit_logs` rows.

------------------------------------------------------------------------

## 5. Security & Privacy

-   **Tenant Isolation:** Postgres `search_path` set per request using
    Clerk `org_id`.
-   **Encryption:** All sensitive fields are encrypted with Vault before
    storage.
-   **Sanitization:** Emails, IBANs, phone numbers are stripped or
    masked before sending to LLMs.
-   **Auditability:** Every apply‑action is logged in `audit_logs`
    (JSONB).

------------------------------------------------------------------------

## 6. Front‑End Setup

### 6.1 React + Clerk

-   Uses ClerkProvider + `<SignedIn>` / `<SignedOut>` for auth gates.
-   Dev mode uses fake auth but code is ready to switch to real JWT
    validation.

### 6.2 Layout

Three‑pane layout: 1. **Chat input** (thread + message creation) 2.
**Answer panel** (3 provider cards with Append/Replace buttons) 3.
**Monaco editor** (editable doc)

### 6.3 State

-   Zustand store keeps:
    -   `document`, `threadId`, `messages`, `answers`, `lastRequestId`
-   `askAI()` posts message → `/ai/compare` → sets `answers`
-   `pickAnswer()` posts to `/ai/selection` → refreshes doc.

------------------------------------------------------------------------

## 7. Conversation Memory

-   When user clicks Append/Replace → chosen text is saved as
    `assistant` message in `chat_messages`.
-   On next `/ai/compare`, entire history (user + assistant turns) is
    replayed to **all three providers** so follow‑ups have context.
-   History is clipped by `MAX_HISTORY_CHARS` (configurable).

------------------------------------------------------------------------

## 8. Dev & Debugging Notes

### 8.1 Run Infra

``` bash
cd lumen/infra
docker compose --env-file ./.env up -d
```

### 8.2 Run API

``` bash
cd lumen/api
source .venv/bin/activate
python -m app.main
```

### 8.3 Run Front‑End

``` bash
cd lumen/web
npm run dev
```

### 8.4 Inspect DB

Using TablePlus or psql:

``` sql
SELECT id, title FROM mem_01.documents;
SELECT action, jsonb_pretty(details) FROM mem_01.audit_logs ORDER BY created_at DESC LIMIT 5;
```

------------------------------------------------------------------------

## 9. Next Steps (Future Stages)

-   Add token‑aware history truncation.
-   Implement `/documents/:id/versions` diff API.
-   Replace dev auth with real Clerk JWT verification middleware.
-   Add prompt optimization + per‑provider performance tracking.
-   Add background learning jobs for meta‑routing.

------------------------------------------------------------------------

**End of Stage 1 Documentation** -- this file serves as your personal
technical reference for everything set up so far.
