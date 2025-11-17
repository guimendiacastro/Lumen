# LUMEN APPLICATION DATA STORAGE & LLM INTEGRATION DOCUMENTATION

## Executive Summary

LUMEN is a multi-tenant legal drafting application with enterprise-grade security featuring:
- Multi-tenant PostgreSQL architecture with per-organization schema isolation
- End-to-end encryption using HashiCorp Vault Transit Engine
- PII sanitization before sending data to LLM providers
- Flexible RAG (Retrieval Augmented Generation) with three implementation options
- Support for multiple LLM providers (OpenAI GPT, Anthropic Claude, xAI Grok)

---

## 1. DATABASE SCHEMA ARCHITECTURE

### 1.1 Multi-Tenant Design

LUMEN uses a **schema-per-tenant** approach within a single PostgreSQL database:

- **Control Schema (`control`)**: Global tenant mapping (no sensitive client data)
- **Member Schemas (`mem_01`, `mem_02`, etc.)**: Per-organization isolated schemas with all client data

### 1.2 Control Schema Tables

#### Table: `control.members`
```sql
CREATE TABLE control.members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id TEXT UNIQUE NOT NULL,           -- Clerk Organization ID
  name TEXT NOT NULL,
  specialization TEXT NOT NULL,
  schema_name TEXT NOT NULL UNIQUE,      -- e.g., mem_01, mem_02
  vault_key_id TEXT NOT NULL,            -- e.g., transit/keys/member_01
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Purpose**: Maps external organization IDs (from Clerk authentication) to:
- An isolated PostgreSQL schema
- A dedicated Vault encryption key

#### Table: `control.users`
```sql
CREATE TABLE control.users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clerk_user_id TEXT UNIQUE NOT NULL,
  org_id TEXT NOT NULL,                  -- Links to members.org_id
  role TEXT NOT NULL,                    -- admin | lawyer | support
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Purpose**: Maps individual users to organizations and defines their roles.

### 1.3 Per-Member Schema Tables

Each member schema contains identical table structures:

#### Table: `{schema}.documents`
```sql
CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  content_enc BYTEA NOT NULL,           -- Encrypted document content
  mime TEXT DEFAULT 'text/markdown',
  created_by TEXT NOT NULL,
  updated_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Encryption**: `content_enc` stores the encrypted document text (encrypted via Vault).

#### Table: `{schema}.doc_versions`
```sql
CREATE TABLE doc_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  version INT NOT NULL,
  content_enc BYTEA NOT NULL,           -- Encrypted version content
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(document_id, version)
);
```

**Purpose**: Maintains version history for documents.

#### Table: `{schema}.chat_threads`
```sql
CREATE TABLE chat_threads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NULL REFERENCES documents(id) ON DELETE SET NULL,
  title TEXT,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Purpose**: Conversation threads, optionally linked to a document.

#### Table: `{schema}.chat_messages`
```sql
CREATE TABLE chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id UUID NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
  role TEXT NOT NULL,                   -- 'user' or 'system'
  raw_hash TEXT NOT NULL,               -- SHA-256 hash of original text
  text_enc BYTEA NOT NULL,              -- Encrypted ORIGINAL text with PII
  sanitized_enc BYTEA NOT NULL,         -- Encrypted SANITIZED text (PII removed)
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Critical Security Feature**: DUAL ENCRYPTION
- `text_enc`: Original user input with PII intact (for internal use only)
- `sanitized_enc`: PII-redacted version (sent to LLM providers)

#### Table: `{schema}.ai_requests`
```sql
CREATE TABLE ai_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id UUID NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
  message_id UUID NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
  scope TEXT NOT NULL,                  -- 'full' or other scope indicators
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Purpose**: Tracks each AI request for auditing.

#### Table: `{schema}.ai_responses`
```sql
CREATE TABLE ai_responses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id UUID NOT NULL REFERENCES ai_requests(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,               -- 'openai', 'anthropic', 'xai'
  text_enc BYTEA NOT NULL,              -- Encrypted AI response
  input_tokens INT,
  output_tokens INT,
  latency_ms INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Purpose**: Stores responses from multiple LLM providers with performance metrics.

#### Table: `{schema}.ai_selections`
```sql
CREATE TABLE ai_selections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id UUID NOT NULL REFERENCES ai_requests(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  selection_meta JSONB,
  applied_to_document UUID NULL REFERENCES documents(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Purpose**: Tracks which AI response the user selected and applied.

#### Table: `{schema}.uploaded_files`
```sql
CREATE TABLE uploaded_files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NULL REFERENCES documents(id) ON DELETE CASCADE,
  thread_id UUID NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  file_size_bytes BIGINT NOT NULL,
  storage_path TEXT NOT NULL,           -- e.g., 'local/{file_id}' or blob URL
  content_enc BYTEA NOT NULL,           -- Encrypted full file content
  status TEXT NOT NULL DEFAULT 'processing',  -- 'processing', 'ready', 'error'
  error_message TEXT,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ
);
```

**Purpose**: Tracks uploaded files attached to threads or documents.

#### Table: `{schema}.audit_logs`
```sql
CREATE TABLE audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  target TEXT,
  details JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Purpose**: Comprehensive audit trail.

### 1.4 Foreign Key Relationships

```
documents (1) ─┬─> (N) doc_versions
               └─> (N) chat_threads ──> (N) chat_messages
                                            └─> (N) ai_requests ─┬─> (N) ai_responses
                                                                 └─> (N) ai_selections

chat_threads (1) ──> (N) uploaded_files
documents (1) ──> (N) uploaded_files
```

---

## 2. ENCRYPTION & STORAGE

### 2.1 HashiCorp Vault Transit Engine

LUMEN uses Vault's **Transit** secrets engine for encryption-as-a-service:

```python
# Environment Configuration
VAULT_ADDR = "http://localhost:8200"
VAULT_TOKEN = "dev-token"
TRANSIT_MOUNT = "transit"
```

#### Key Functions

**Encryption**:
```python
async def encrypt_text(key_path: str, plaintext: str) -> bytes:
    """
    Encrypt plaintext using Vault Transit.
    Returns UTF-8 bytes of the Vault ciphertext (e.g., b'vault:v1:...')
    ready to store in BYTEA.
    """
```

**Decryption**:
```python
async def decrypt_text(key_path: str, ciphertext_bytes: bytes) -> str:
    """
    Decrypt Vault ciphertext (stored as BYTEA) back to plaintext string.
    """
```

**Key Features**:
- Data encrypted/decrypted via HTTP API calls to Vault
- Encryption keys NEVER leave Vault
- Base64 encoding for transport
- Each organization has its own encryption key (e.g., `transit/keys/member_01`)

### 2.2 Key Rotation & Security

- **Per-Tenant Keys**: Each member schema has a dedicated Vault key
- **Key Creation**: Automated during onboarding
- **No Local Keys**: Encryption keys are never stored in the application
- **Versioned Encryption**: Vault's `vault:v1:...` format supports key rotation

### 2.3 Encrypted Fields

| Table | Field | Content Type |
|-------|-------|-------------|
| `documents` | `content_enc` | Full document content |
| `doc_versions` | `content_enc` | Version snapshot |
| `chat_messages` | `text_enc` | Original user message (with PII) |
| `chat_messages` | `sanitized_enc` | Sanitized user message (PII removed) |
| `ai_responses` | `text_enc` | AI provider response |
| `uploaded_files` | `content_enc` | Full file content |

### 2.4 Understanding `text_enc` vs `sanitized_enc`

When a user posts a message:

```python
raw = payload.text
sanitized_text = sanitize(raw)  # PII removal
raw_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

raw_enc = await encrypt_text(key_id, raw)              # Original with PII
sanitized_enc = await encrypt_text(key_id, sanitized_text)  # PII removed

# Both versions stored in database
```

**Why Both?**:
- `text_enc`: Preserves original for legal compliance, internal review
- `sanitized_enc`: Sent to external LLM APIs (privacy protection)

---

## 3. PRIVACY & SANITIZATION

### 3.1 Sanitization Rules

Current implementation uses regex patterns:

```python
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
IBAN  = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
PT_NIF = re.compile(r"\b\d{9}\b")

def sanitize(text: str) -> str:
    t = EMAIL.sub("[EMAIL]", text)
    t = PHONE.sub("[PHONE]", t)
    t = IBAN.sub("[IBAN]", t)
    t = PT_NIF.sub("[PT_TAX]", t)
    return t
```

### 3.2 PII Redaction Examples

| Original | Sanitized |
|----------|-----------|
| `Contact john@example.com` | `Contact [EMAIL]` |
| `Call +351 912 345 678` | `Call [PHONE]` |
| `Account PT50 0002 0123 12345678901` | `Account [IBAN]` |
| `Tax ID 123456789` | `Tax ID [PT_TAX]` |

### 3.3 What Goes to LLM Providers?

**ALWAYS SANITIZED**: Only `sanitized_enc` is decrypted and sent to LLMs.

```python
async def _load_sanitized_message(schema: str, key_id: str, message_id: str) -> str:
    """Load the sanitized version of a specific message."""
    # Retrieves sanitized_enc only
```

---

## 4. FILE UPLOAD & RAG SYSTEM

### 4.1 File Processing Pipeline

#### Step 1: Text Extraction

```python
class FileProcessor:
    @staticmethod
    def extract_text_from_pdf(content: bytes) -> str:
        """Extract text from PDF using PyPDF2."""

    @staticmethod
    def extract_text_from_docx(content: bytes) -> str:
        """Extract text from DOCX using python-docx."""
```

**Supported Formats**:
- PDF (via PyPDF2)
- DOCX (via python-docx)
- Plain text (UTF-8)

#### Step 2: Size-Based Strategy Decision

```python
MAX_DIRECT_CONTEXT_CHARS = 50000

def process_file(content: bytes, mime_type: str) -> FileProcessingResult:
    text = extract_text_from_file(content, mime_type)
    use_direct = len(text) <= MAX_DIRECT_CONTEXT_CHARS

    return FileProcessingResult(
        use_direct_context=use_direct,  # True = include directly in prompt
        full_text=text,
        total_size=len(text)
    )
```

**Strategy**:
- Files ≤ 50,000 chars: Include full text directly in LLM prompt
- Files > 50,000 chars: Use RAG (chunk, embed, retrieve relevant sections)

### 4.2 File Storage

```python
# Encrypt full text
content_enc = await encrypt_text(key_id, result.full_text)

# Store file record in uploaded_files table
```

**Current Storage**: Encrypted file content stored in PostgreSQL `BYTEA` column.

### 4.3 RAG Service Implementations

LUMEN supports **three RAG implementations** via feature flags:

#### Option 1: Legacy Qdrant RAG (Default)

**Architecture**:
```
┌──────────────────┐
│ File Upload      │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ LlamaIndex       │ - Sentence Window Chunking
│ HuggingFace      │ - BAAI/bge-large-en-v1.5 embeddings
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Qdrant Vector DB │ - Per-file collections
│ (Self-hosted)    │ - HNSW indexing
└──────────────────┘
```

**Configuration**:
```bash
QDRANT_HOST=localhost
QDRANT_PORT=6333
EMBEDDING_MODEL=BAAI/bge-large-en-v1.5
CHUNK_SIZE=512
CHUNK_OVERLAP=50
```

**Key Features**:
- Sentence window node parser (3-sentence context)
- 1024-dimensional embeddings
- Per-file Qdrant collections (`file_{file_id}`)
- Cosine similarity search

#### Option 2: Azure RAG (Manual Chunking)

**Architecture**:
```
┌──────────────────┐
│ File Upload      │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Python Chunking  │ - Character-based with sentence boundary detection
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Azure OpenAI     │ - text-embedding-3-small
│ Embeddings API   │ - 1536 dimensions
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Azure AI Search  │ - Single shared index: lumen-file-chunks
│                  │ - Hybrid search (vector + keyword)
└──────────────────┘
```

**Enable**: `USE_AZURE=true`

**Configuration**:
```bash
AZURE_SEARCH_ENDPOINT=https://....search.windows.net
AZURE_SEARCH_KEY=...
AZURE_OPENAI_EMBEDDING_ENDPOINT=https://....openai.azure.com/
AZURE_OPENAI_EMBEDDING_KEY=...
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
INDEX_NAME=lumen-file-chunks
```

**Index Schema**:
```python
fields = [
    SimpleField(name="chunk_id", type=String, key=True, filterable=True),
    SimpleField(name="file_id", type=String, filterable=True),
    SearchableField(name="text", type=String, searchable=True),
    SearchableField(name="filename", type=String, searchable=True, filterable=True),
    SearchField(name="text_vector", type=Collection(Single),
                vector_search_dimensions=1536),
    SimpleField(name="chunk_index", type=Int32, filterable=True, sortable=True),
]
```

#### Option 3: Azure Integrated Vectorization (Most Advanced)

**Architecture**:
```
┌──────────────────┐
│ File Upload      │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Azure Blob       │ - Raw file storage
│ Storage          │ - Metadata tagging
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Azure AI Search  │ AUTOMATIC PIPELINE:
│ Indexer          │ 1. SplitSkill (chunking)
│                  │ 2. AzureOpenAIEmbeddingSkill (embeddings)
└────────┬─────────┘ 3. Indexing
         │
         ▼
┌──────────────────┐
│ Azure AI Search  │ - Index: lumen-files-integrated
│ Index            │ - No manual Python chunking/embedding!
└──────────────────┘
```

**Enable**: `USE_AZURE=true` + `USE_INTEGRATED_VECTORIZATION=true`

**Configuration**:
```bash
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
AZURE_STORAGE_CONTAINER=lumen-documents
```

**Key Advantage**: Eliminates Python-side chunking and embedding API calls. Azure handles everything automatically via indexer pipeline.

### 4.4 Vector Storage Comparison

| Feature | Qdrant (Legacy) | Azure Manual | Azure Integrated |
|---------|----------------|--------------|------------------|
| **Vector DB** | Self-hosted Qdrant | Azure AI Search | Azure AI Search |
| **Embeddings** | HuggingFace (local) | Azure OpenAI API | Azure OpenAI (automatic) |
| **Chunking** | LlamaIndex (Python) | Python code | Azure SplitSkill |
| **Storage** | Per-file collections | Single shared index | Blob + Search index |
| **Scalability** | Limited by server | High | Highest |
| **Cost** | Infrastructure | API calls | API calls + storage |
| **Setup Complexity** | Medium | Medium | High |
| **Query Speed** | Fast | Fast | Fast |

---

## 5. LLM DATA FLOW

### 5.1 LLM Provider Configuration

#### Supported Providers

**OpenAI GPT**:
```bash
# Azure OpenAI (Current)
AZURE_OPENAI_ENDPOINT=https://....openai.azure.com/
AZURE_OPENAI_KEY=...
AZURE_OPENAI_GPT_DEPLOYMENT=gpt-5-chat
AZURE_OPENAI_API_VERSION=2025-01-01-preview
```

**Anthropic Claude**:
```bash
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-sonnet-20240229
```

**xAI Grok**:
```bash
# Azure AI Foundry (Current)
AZURE_AI_FOUNDRY_ENDPOINT=https://....models.ai.azure.com/
AZURE_AI_FOUNDRY_KEY=...
AZURE_GROK_DEPLOYMENT=grok-4-fast-reasoning
```

#### Feature Flag: Azure Migration

```bash
USE_AZURE=true  # Uses Azure endpoints instead of direct APIs
```

### 5.2 Chat Without Files: Standard Context

#### Data Sent to LLM (No Files)

```python
messages = [
    {"role": "system", "content": system_preamble},  # Task instructions

    # Previous conversation history (sanitized)
    {"role": "system", "content": "Previous requests in this thread:\n1. ..."},

    # Current document (if thread linked to document)
    {"role": "system", "content": "<current_document>\n{content}\n</current_document>"},

    # Latest user instruction (sanitized)
    {"role": "user", "content": latest_instruction}
]
```

**Configuration**:
```python
MAX_DOC_CHARS = 24000  # Max chars from document (clipped from end)
```

### 5.3 Chat With Files: RAG Context

#### Small Files (≤ 50,000 chars): Direct Context

```xml
<uploaded_files>
<file name='contract.txt'>
[Full file content here...]
</file>
</uploaded_files>
```

#### Large Files (> 50,000 chars): RAG Retrieval

**Configuration**:
```python
RAG_TOP_K = 15           # Total chunks to retrieve
RAG_MIN_SIM = 0.7        # Minimum score threshold
```

**Retrieval Strategy**:
```python
chunks = await rag_service.retrieve_from_multiple_files(
    file_ids=file_ids,
    query=query,
    top_k_per_file=max(top_k // len(files), 3),  # Distribute across files
    min_score=min_similarity
)
```

**Output Format**:
```xml
<retrieved_context>
The following information was retrieved from uploaded documents:

[Chunk 1 from contract.pdf] (relevance: 0.89)
Section 3.1: Payment Terms...

[Chunk 2 from contract.pdf] (relevance: 0.85)
Section 5.2: Liability Clauses...

</retrieved_context>
```

### 5.4 Complete LLM Prompt Structure (With Files)

```python
messages = [
    {"role": "system", "content": system_preamble},           # 1. Task definition
    {"role": "system", "content": conversation_history},       # 2. Previous requests
    {"role": "system", "content": current_document_block},     # 3. Document being edited
    {"role": "system", "content": direct_file_context},        # 4. Small files (full content)
    {"role": "system", "content": rag_retrieved_context},      # 5. Large files (chunks)
    {"role": "user", "content": latest_user_instruction}       # 6. Current request
]
```

### 5.5 Fan-Out to Multiple Providers

```python
async def fanout_with_history(messages: list[dict]) -> list[dict]:
    """
    Fan out to all configured providers in parallel.
    """
    tasks = []
    if openai_client:
        tasks.append(call_openai(messages))
    if anthropic_client:
        tasks.append(call_anthropic(messages))
    if xai_client:
        tasks.append(call_xai(messages))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

**Result**: User receives 3 different responses simultaneously for comparison.

### 5.6 Response Storage

```python
# Store encrypted responses
text_enc = await encrypt_text(key_id, expanded_text)
await s.execute(
    text("""
        INSERT INTO ai_responses (request_id, provider, text_enc, input_tokens, output_tokens, latency_ms)
        VALUES (:rid, :prov, :txt, :in_tok, :out_tok, :lat)
    """),
    {
        "rid": request_id,
        "prov": res["provider"],  # 'openai', 'anthropic', 'xai'
        "txt": text_enc,
        "in_tok": res.get("input_tokens"),
        "out_tok": res.get("output_tokens"),
        "lat": res.get("latency_ms"),
    }
)
```

---

## 6. DATA FLOW DIAGRAMS

### 6.1 User Message Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ User submits message: "Draft a termination clause"             │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │ POST /threads/{id}/messages │
         └─────────────┬───────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │ Privacy Sanitization        │
         │ - Remove emails, phones     │
         │ - Remove tax IDs, IBANs     │
         └─────────────┬───────────────┘
                       │
                       ├──────────────────┐
                       ▼                  ▼
         ┌─────────────────┐  ┌─────────────────┐
         │ Encrypt BOTH:   │  │ Store in        │
         │ - Original      │  │ chat_messages   │
         │ - Sanitized     │  │ - text_enc      │
         │ via Vault       │  │ - sanitized_enc │
         └─────────────────┘  └─────────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │ Returns message_id to user  │
         └─────────────────────────────┘
```

### 6.2 AI Request Flow (With RAG)

```
┌─────────────────────────────────────────────────────────────────┐
│ User requests AI response                                       │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │ POST /ai/compare            │
         │ - thread_id                 │
         │ - message_id                │
         └─────────────┬───────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │ Build Context (parallel):   │
         │ 1. Load conversation history│
         │ 2. Load current document    │
         │ 3. Load small files (full)  │
         │ 4. RAG query for large files│
         └─────────────┬───────────────┘
                       │
                       ├───────────┬───────────┐
                       ▼           ▼           ▼
         ┌─────────────┐ ┌─────────┐ ┌─────────┐
         │ OpenAI GPT  │ │ Claude  │ │  Grok   │
         │ (Azure)     │ │(Direct) │ │ (Azure  │
         │             │ │         │ │ Foundry)│
         └─────────────┘ └─────────┘ └─────────┘
                       │           │           │
                       └─────┬─────┴─────┬─────┘
                             ▼           ▼
         ┌─────────────────────────────────────┐
         │ Encrypt & Store 3 Responses         │
         │ - ai_responses table                │
         │ - text_enc (encrypted)              │
         │ - metrics (tokens, latency)         │
         └─────────────────┬───────────────────┘
                           │
                           ▼
         ┌─────────────────────────────────────┐
         │ Return 3 cards to user for selection│
         └─────────────────────────────────────┘
```

### 6.3 File Upload & RAG Indexing Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ User uploads PDF/DOCX file                                      │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │ POST /files/upload          │
         └─────────────┬───────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │ FileProcessor               │
         │ - Extract text (PDF/DOCX)   │
         │ - Check size (<= 50K chars?)│
         └─────────────┬───────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │ Encrypt full text via Vault │
         └─────────────┬───────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │ Store in uploaded_files     │
         │ - content_enc (PostgreSQL)  │
         │ - status = 'processing'     │
         └─────────────┬───────────────┘
                       │
                       ├──── If small file (≤50K chars) ────┐
                       │                                      │
                       │                                      ▼
                       │                    ┌─────────────────────────┐
                       │                    │ Mark status = 'ready'   │
                       │                    │ (No RAG indexing needed)│
                       │                    └─────────────────────────┘
                       │
                       └──── If large file (>50K chars) ────┐
                                                             │
                                                             ▼
                                          ┌─────────────────────────────┐
                                          │ Select RAG Service:         │
                                          │ - Legacy Qdrant             │
                                          │ - Azure Manual              │
                                          │ - Azure Integrated          │
                                          └────────────┬────────────────┘
                                                       │
                   ┌───────────────────────────────────┼───────────────────┐
                   │                                   │                   │
                   ▼                                   ▼                   ▼
    ┌──────────────────────┐         ┌──────────────────────┐  ┌──────────────────────┐
    │ LEGACY QDRANT:       │         │ AZURE MANUAL:        │  │ AZURE INTEGRATED:    │
    │ 1. LlamaIndex chunk  │         │ 1. Python chunk      │  │ 1. Upload to Blob    │
    │ 2. HuggingFace embed │         │ 2. Azure OpenAI embed│  │ 2. Trigger indexer   │
    │ 3. Store in Qdrant   │         │ 3. Store in AI Search│  │ 3. Azure auto-chunks │
    │    (per-file coll.)  │         │    (shared index)    │  │    & embeds          │
    └──────────────────────┘         └──────────────────────┘  └──────────────────────┘
                   │                                   │                   │
                   └───────────────────────────────────┴───────────────────┘
                                                       │
                                                       ▼
                                          ┌─────────────────────────────┐
                                          │ Update uploaded_files       │
                                          │ status = 'ready'            │
                                          └─────────────────────────────┘
```

---

## 7. SECURITY & PRIVACY SUMMARY

### 7.1 Data Protection Layers

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Tenant Isolation** | PostgreSQL Schemas | Prevent cross-tenant data access |
| **Encryption at Rest** | Vault Transit | All sensitive data encrypted in DB |
| **PII Sanitization** | Regex patterns | Remove personal info before LLM |
| **Dual Storage** | text_enc + sanitized_enc | Preserve original + protect privacy |
| **Key Management** | HashiCorp Vault | Centralized, rotatable keys |
| **Audit Trail** | audit_logs table | Track all actions |

### 7.2 What Data Goes Where?

| Destination | Data Sent | PII Status |
|-------------|-----------|------------|
| **PostgreSQL** | All data (encrypted) | Original + Sanitized |
| **Vault** | None (only API calls) | N/A |
| **LLM Providers** | Sanitized messages + context | PII Removed |
| **Vector DB** | File chunks (Qdrant) or embeddings (Azure) | Raw text (indexed) |
| **Azure Blob** | Raw file content (Integrated mode) | Raw text |

### 7.3 Data Never Sent to LLMs

- Original user messages with PII (only `sanitized_enc` sent)
- User IDs, org IDs, internal UUIDs
- Encryption keys (always in Vault)

---

## 8. CONFIGURATION SUMMARY

### 8.1 Environment Variables

#### Database
```bash
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/lumen
```

#### Vault Encryption
```bash
VAULT_ADDR=http://localhost:8200
VAULT_TOKEN=dev-token
VAULT_TRANSIT_MOUNT=transit
```

#### LLM Providers
```bash
# Feature Flag
USE_AZURE=true

# OpenAI (Azure)
AZURE_OPENAI_ENDPOINT=https://....openai.azure.com/
AZURE_OPENAI_KEY=...
AZURE_OPENAI_GPT_DEPLOYMENT=gpt-5-chat
AZURE_OPENAI_API_VERSION=2025-01-01-preview

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-sonnet-20240229

# xAI (Azure AI Foundry)
AZURE_AI_FOUNDRY_ENDPOINT=https://....models.ai.azure.com/
AZURE_AI_FOUNDRY_KEY=...
AZURE_GROK_DEPLOYMENT=grok-4-fast-reasoning
```

#### RAG Services
```bash
# Legacy Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
EMBEDDING_MODEL=BAAI/bge-large-en-v1.5
CHUNK_SIZE=512
CHUNK_OVERLAP=50

# Azure RAG
USE_INTEGRATED_VECTORIZATION=false
AZURE_SEARCH_ENDPOINT=https://....search.windows.net
AZURE_SEARCH_KEY=...
AZURE_SEARCH_INDEX_NAME=lumen-file-chunks
AZURE_OPENAI_EMBEDDING_ENDPOINT=https://....openai.azure.com/
AZURE_OPENAI_EMBEDDING_KEY=...
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small

# Azure Integrated Vectorization
USE_INTEGRATED_VECTORIZATION=true
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
AZURE_STORAGE_CONTAINER=lumen-documents
```

#### RAG Tuning
```bash
RAG_TOP_K=15                  # Total chunks to retrieve
RAG_MIN_SIMILARITY=0.7        # Minimum score threshold
MAX_DOC_CHARS=24000           # Max document chars in prompt
```

---

## 9. KEY TAKEAWAYS

1. **Multi-Tenant Architecture**: Each organization gets isolated PostgreSQL schema + Vault key

2. **Dual Encryption Strategy**:
   - Store original messages (`text_enc`) for compliance
   - Store sanitized messages (`sanitized_enc`) for LLM use

3. **Three RAG Options**:
   - Legacy: Self-hosted Qdrant + HuggingFace
   - Azure Manual: Python chunking + Azure AI Search
   - Azure Integrated: Blob Storage + automatic indexer pipeline

4. **Privacy First**: PII is removed before any data goes to LLM providers

5. **Flexible File Handling**:
   - Small files (≤50K): Full context in prompt
   - Large files (>50K): RAG retrieval of relevant chunks

6. **Multi-Provider LLM**: Parallel queries to OpenAI, Anthropic, and xAI for user comparison

7. **Complete Audit Trail**: All AI requests, responses, and user selections tracked

8. **Azure Migration Path**: Feature flags enable gradual transition from self-hosted to Azure services

---

**Document Version**: 1.0
**Last Updated**: 2025-11-05
**Generated By**: Claude Code Agent
