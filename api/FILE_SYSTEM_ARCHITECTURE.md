# LUMEN File System Architecture

## Overview

LUMEN is a legal document AI system that processes uploaded files (PDFs, DOCX, etc.) and makes them available for AI-powered Q&A using RAG (Retrieval Augmented Generation). The system uses a **hybrid approach** that combines direct context (for small files) with RAG (for large files).

## Architecture Diagram

```
Upload → Text Extraction → Size Decision → Storage Path
                             ↓
                    ┌────────┴────────┐
                    ↓                 ↓
              Direct Context      RAG Path
              (≤ 500k chars)    (> 500k chars)
                    ↓                 ↓
              Store in DB      Chunk + Embed + Index
                    ↓                 ↓
              LLM Prompt       Vector Search → LLM
```

## 1. File Upload Flow

### Entry Point
**Route**: `POST /files/upload`  
**File**: [`api/app/routers/files.py`](file:///Users/gui/Desktop/lumen/lumen/api/app/routers/files.py)

```python
@router.post("/files/upload")
async def upload_file(
    file: UploadFile,
    thread_id: Optional[str] = None,
    ...
)
```

### What Happens
1. **Validation**: Check file size (max 200MB), MIME type
2. **Processing**: Call `FileProcessor.process_file()`
3. **Encryption**: Encrypt text using HashiCorp Vault
4. **Storage**: Save to PostgreSQL `uploaded_files` table
5. **Indexing**: If large file, trigger RAG indexing

## 2. Text Extraction

### Service
**File**: [`api/app/services/file_processor.py`](file:///Users/gui/Desktop/lumen/lumen/api/app/services/file_processor.py)

### Extraction Strategy by File Type

#### PDF Files
```python
1. Try PyPDF2 first (fast text extraction)
2. Check quality: avg_chars_per_page < 50?
   ├─ YES → Scanned PDF detected → Use Azure OCR
   └─ NO → Use PyPDF2 text
```

**PyPDF2 Path**:
- Library: `PyPDF2.PdfReader`
- Speed: Fast (~1 second for 400 pages)
- Output: Plain text
- Limitation: No page metadata, no structure preservation

**Azure OCR Path**:
- Service: Azure Document Intelligence (`prebuilt-layout` model)
- File: [`api/app/services/azure_ocr_service.py`](file:///Users/gui/Desktop/lumen/lumen/api/app/services/azure_ocr_service.py)
- Speed: Slow (~2-3 seconds/page)
- Output: **Markdown format** (preserves headers, tables, structure)
- Page limit (free tier): 2 pages
- Page limit (paid tier): 2000 pages

#### DOCX Files
```python
# Uses python-docx library
doc = DocxDocument(file_bytes)
text = '\n'.join([para.text for para in doc.paragraphs])
```

#### Other Files
```python
# Try UTF-8 decode
text = content.decode('utf-8')
```

### Output
Returns `FileProcessingResult`:
```python
@dataclass
class FileProcessingResult:
    text: str                    # Extracted text
    use_direct_context: bool     # True if ≤ 500k chars
    char_count: int             # Total characters
```

## 3. Storage Decision (Direct Context vs RAG)

### Decision Logic
**File**: [`api/app/services/file_processor.py`](file:///Users/gui/Desktop/lumen/lumen/api/app/services/file_processor.py)

```python
MAX_DIRECT_CONTEXT_CHARS = 500000  # ~125k tokens

if len(extracted_text) <= MAX_DIRECT_CONTEXT_CHARS:
    use_direct_context = True   # Send entire text to LLM
else:
    use_direct_context = False  # Use RAG (chunk + embed + index)
```

### Why 500k Characters?
- Modern LLMs support massive context windows:
  - GPT-4o: 128k tokens (~500k chars)
  - Claude 3.5: 200k tokens (~800k chars)
  - Gemini 1.5 Pro: 2M tokens (~8M chars)
- For legal documents, **holistic reasoning** (seeing the whole doc) is better than chunking
- 500k limit covers ~95% of contracts and legal documents

## 4. Storage Paths

### Path A: Direct Context (Small Files)

**Storage**: PostgreSQL `uploaded_files` table

```sql
uploaded_files (
    content_enc BYTEA,           -- Encrypted full text
    use_direct_context BOOLEAN,  -- TRUE
    ...
)
```

**Usage**: When user asks a question
1. Decrypt full text from DB
2. Insert entire text into LLM prompt
3. LLM sees the **whole document** for better reasoning

**Advantages**:
- Simple, fast retrieval
- No chunking artifacts
- Better for cross-referencing within a single document

### Path B: RAG (Large Files)

**Components**:
1. **Local Chunking** (your server)
2. **Azure OpenAI** (embeddings)
3. **Azure AI Search** (vector index)

#### Step 1: Chunking
**File**: [`api/app/services/azure_rag_service.py`](file:///Users/gui/Desktop/lumen/lumen/api/app/services/azure_rag_service.py)  
**Class**: `LocalChunker`

```python
# Configuration
CHUNK_SIZE = 800 tokens
CHUNK_OVERLAP = 200 tokens

# Strategy
1. Split by paragraphs (\n\n)
2. Combine paragraphs up to 800 tokens
3. Overlap by 200 tokens (context continuity)
4. Track Markdown headers (for section metadata)
5. Track page numbers (when available)
```

**Output**: `DocumentChunk` objects
```python
@dataclass
class DocumentChunk:
    content: str              # Chunk text
    chunk_index: int          # Position in document
    token_count: int          # Number of tokens
    section_header: str       # Markdown header (e.g., "Article 1828")
    page_number: int          # Page number (if available)
```

#### Step 2: Generate Embeddings
**Service**: Azure OpenAI `text-embedding-ada-002`

```python
# For each chunk:
chunk_text → Azure OpenAI → 1536-dimensional vector

# Batch processing
Chunks sent in batches of 16 to minimize API calls
```

#### Step 3: Upload to Azure AI Search
**Service**: Azure AI Search  
**Index**: `lumen-documents`

**Schema**:
```python
{
    "id": "file_id_chunk_index",
    "file_id": "UUID",
    "org_id": "security_filter",
    "user_id": "security_filter",
    "filename": "codigo_civil.pdf",
    "content": "Full chunk text",
    "chunk_index": 0,
    "page_number": 321,
    "section_header": "Article 1828",
    "content_vector": [0.123, 0.456, ...],  # 1536 dimensions
}
```

**Security**: Every document tagged with `org_id` and `user_id` for multi-tenancy

## 5. Query Flow (RAG)

### When User Asks a Question

**File**: [`api/app/routers/ai.py`](file:///Users/gui/Desktop/lumen/lumen/api/app/routers/ai.py)  
**Function**: `_get_rag_context()`

```python
1. User question → Azure OpenAI → query embedding (vector)
2. Vector search in Azure AI Search
   - Compare query vector with all chunk vectors
   - Apply security filters (org_id, user_id, file_ids)
   - Return top 15 most similar chunks
3. Format chunks into prompt:
   [Chunk 1 from file.pdf] [Page 321] [Section: Article 1828] (relevance: 0.89)
   <chunk content>
4. Send to LLM with retrieved context
```

### RAG Prompt Structure

```
[System Instructions]

[Current Document] (if editing mode)

[Retrieved Context]
<retrieved_context>
The following information was retrieved from uploaded documents:

[Chunk 1 from codigo_civil.pdf] [Page 321] [Section: Article 1828] (relevance: 0.89)
Relativamente ao filho nascido dentro dos cento e oitenta dias...

[Chunk 2 from codigo_civil.pdf] [Page 322] (relevance: 0.87)
...
</retrieved_context>

[User Question]
A child is born 160 days after the celebration of a marriage...
```

## 6. Key Features

### Security
- **Multi-tenancy**: All queries filtered by `org_id` and `user_id`
- **Encryption**: All file content encrypted with HashiCorp Vault
- **Ownership verification**: Users can only access their own files

### Metadata for Better Citations
```python
{
    "section_header": "Article 1828",  # From Markdown headers
    "page_number": 321,                # From Azure OCR (when available)
    "filename": "codigo_civil.pdf",
    "chunk_index": 45
}
```

**LLM can cite**: "According to Article 1828 on page 321..."

### Hybrid Search Ready
Current: **Pure vector search**  
Future: Can add **hybrid search** (keyword + semantic) for better legal term matching

## 7. Configuration

### Environment Variables

```bash
# File Processing
MAX_DIRECT_CONTEXT_CHARS=500000

# Azure Document Intelligence (OCR)
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://...
AZURE_DOCUMENT_INTELLIGENCE_KEY=...

# Azure AI Search (RAG)
AZURE_SEARCH_ENDPOINT=https://...
AZURE_SEARCH_KEY=...
AZURE_SEARCH_INDEX_NAME=lumen-documents

# Azure OpenAI (Embeddings)
AZURE_OPENAI_EMBEDDING_ENDPOINT=https://...
AZURE_OPENAI_EMBEDDING_KEY=...
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-ada-002

# RAG Tuning
RAG_TOP_K=15                  # Number of chunks to retrieve
RAG_MIN_SIMILARITY=0.7        # Minimum relevance score
EMBEDDING_BATCH_SIZE=16       # Chunks per embedding API call
```

### Database Schema

```sql
-- File metadata
CREATE TABLE uploaded_files (
    id UUID PRIMARY KEY,
    thread_id UUID REFERENCES chat_threads(id),
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    content_enc BYTEA NOT NULL,           -- Encrypted text
    use_direct_context BOOLEAN,           -- Direct context flag
    status TEXT DEFAULT 'processing',     -- processing/ready/error
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

## 8. Performance Characteristics

### Direct Context Path
- **Upload Time**: 1-5 seconds (extraction + encryption + DB write)
- **Query Time**: 50-200ms (decrypt + add to prompt)
- **Best For**: Contracts, single documents, holistic reasoning

### RAG Path
- **Upload Time**: 
  - Extraction: 1-5 seconds
  - Chunking: < 1 second (local)
  - Embeddings: ~4 seconds/100 chunks (Azure OpenAI)
  - Indexing: 1-2 seconds (Azure Search)
  - **Total**: ~1 minute for 400-page document
- **Query Time**:
  - Embedding: 0.2s (Azure OpenAI)
  - Search: 0.1s (Azure Search)
  - **Total**: 0.3s for retrieval
- **Best For**: Large document collections, discovery, multi-document search

## 9. Cost Analysis

### Direct Context (Small Files)
- **Azure Costs**: $0 (uses main LLM context)
- **Limitation**: Token costs for large context windows

### RAG (Large Files)
- **Embeddings**: $0.0001/1k tokens (Azure OpenAI)
  - 400-page document (~800 chunks) ≈ $0.08
- **Search**: ~$0.50/month for 1GB storage
- **OCR** (if needed): $0.01/page (Azure Document Intelligence)
  - 400-page scan ≈ $4.00

## 10. Files Reference

| File | Purpose |
|------|---------|
| [`files.py`](file:///Users/gui/Desktop/lumen/lumen/api/app/routers/files.py) | Upload endpoint, orchestration |
| [`file_processor.py`](file:///Users/gui/Desktop/lumen/lumen/api/app/services/file_processor.py) | Text extraction, size decision |
| [`azure_ocr_service.py`](file:///Users/gui/Desktop/lumen/lumen/api/app/services/azure_ocr_service.py) | OCR for scanned PDFs |
| [`azure_rag_service.py`](file:///Users/gui/Desktop/lumen/lumen/api/app/services/azure_rag_service.py) | Chunking, embeddings, indexing |
| [`ai.py`](file:///Users/gui/Desktop/lumen/lumen/api/app/routers/ai.py) | RAG retrieval, prompt construction |

## Summary

LUMEN uses a **modern hybrid architecture** that:
1. **Extracts text** using PyPDF2 or Azure OCR
2. **Decides** based on size: Direct Context (small) vs RAG (large)
3. **Stores** encrypted in PostgreSQL (direct) or Azure AI Search (RAG)
4. **Retrieves** via full text (direct) or vector similarity (RAG)
5. **Provides** rich metadata (section headers, page numbers) for citations

This approach balances **quality** (holistic reasoning for single docs) with **scalability** (RAG for large collections).
