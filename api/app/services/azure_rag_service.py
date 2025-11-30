# lumen/api/app/services/azure_rag_service.py
"""
Azure RAG Service with LOCAL high-performance chunking and Azure AI Search for storage/retrieval.

Architecture:
- Local chunking: Uses semantic chunking with overlap for optimal retrieval performance
- Azure AI Search: Stores chunks with embeddings and provides vector search
- Azure OpenAI: Generates embeddings for chunks
"""

import os
import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.models import VectorizedQuery
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticField,
    SemanticSearch,
)
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from openai import AsyncAzureOpenAI, RateLimitError

import tiktoken

log = logging.getLogger("lumen.rag")

# Environment variables
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME", "lumen-documents")

AZURE_OPENAI_EMBEDDING_ENDPOINT = os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT")
AZURE_OPENAI_EMBEDDING_KEY = os.getenv("AZURE_OPENAI_EMBEDDING_KEY")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
AZURE_OPENAI_EMBEDDING_API_VERSION = os.getenv("AZURE_OPENAI_EMBEDDING_API_VERSION", "2023-05-15")

# Chunking configuration for optimal performance
CHUNK_SIZE = 800  # tokens - optimal for semantic coherence and retrieval
CHUNK_OVERLAP = 200  # tokens - ensures context continuity across chunks
EMBEDDING_DIMENSIONS = 1536  # text-embedding-ada-002 dimensions
EMBEDDING_BATCH_SIZE = int(os.getenv("AZURE_OPENAI_EMBEDDING_BATCH_SIZE", "16"))
EMBEDDING_MAX_RETRIES = int(os.getenv("AZURE_OPENAI_EMBEDDING_MAX_RETRIES", "5"))
EMBEDDING_RETRY_DELAY = float(os.getenv("AZURE_OPENAI_EMBEDDING_RETRY_DELAY", "2"))


@dataclass
class DocumentChunk:
    """Represents a chunk of text with metadata"""
    content: str
    chunk_index: int
    token_count: int
    char_start: int
    char_end: int
    section_header: Optional[str] = None
    page_number: Optional[int] = None


class LocalChunker:
    """High-performance local text chunker with semantic awareness"""

    def __init__(self, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding

    def chunk_text(self, text: str) -> List[DocumentChunk]:
        """
        Chunk text using semantic boundaries and token-based splitting.
        Now supports Markdown header tracking for better context.
        """
        chunks = []

        # Split into paragraphs
        paragraphs = text.split('\n\n')

        current_chunk = []
        current_tokens = 0
        char_position = 0
        chunk_start_char = 0
        chunk_index = 0
        current_header = None
        
        # Helper to check for headers
        def get_header(text: str) -> Optional[str]:
            lines = text.split('\n')
            for line in lines:
                if line.strip().startswith('#'):
                    return line.strip().lstrip('#').strip()
            return None

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # Check if paragraph contains a header
            new_header = get_header(para)
            if new_header:
                current_header = new_header

            para_tokens = self.encoding.encode(para)
            para_token_count = len(para_tokens)

            # If single paragraph is too large, split by sentences
            if para_token_count > self.chunk_size:
                # Save current chunk if exists
                if current_chunk:
                    chunk_text = '\n\n'.join(current_chunk)
                    chunks.append(DocumentChunk(
                        content=chunk_text,
                        chunk_index=chunk_index,
                        token_count=current_tokens,
                        char_start=chunk_start_char,
                        char_end=char_position,
                        section_header=current_header
                    ))
                    chunk_index += 1

                # Split large paragraph by sentences
                sentences = self._split_sentences(para)
                sentence_chunk = []
                sentence_tokens = 0
                sentence_start = char_position

                for sentence in sentences:
                    sent_tokens = self.encoding.encode(sentence)
                    sent_token_count = len(sent_tokens)

                    if sentence_tokens + sent_token_count > self.chunk_size and sentence_chunk:
                        # Save sentence chunk
                        chunk_text = ' '.join(sentence_chunk)
                        chunks.append(DocumentChunk(
                            content=chunk_text,
                            chunk_index=chunk_index,
                            token_count=sentence_tokens,
                            char_start=sentence_start,
                            char_end=char_position,
                            section_header=current_header
                        ))
                        chunk_index += 1

                        # Add overlap from previous chunk
                        overlap_text = self._get_overlap_text(sentence_chunk, self.chunk_overlap)
                        sentence_chunk = [overlap_text] if overlap_text else []
                        sentence_tokens = len(self.encoding.encode(' '.join(sentence_chunk)))
                        sentence_start = char_position

                    sentence_chunk.append(sentence)
                    sentence_tokens += sent_token_count
                    char_position += len(sentence) + 1

                # Save remaining sentences
                if sentence_chunk:
                    chunk_text = ' '.join(sentence_chunk)
                    chunks.append(DocumentChunk(
                        content=chunk_text,
                        chunk_index=chunk_index,
                        token_count=sentence_tokens,
                        char_start=sentence_start,
                        char_end=char_position,
                        section_header=current_header
                    ))
                    chunk_index += 1

                # Reset for next paragraph
                current_chunk = []
                current_tokens = 0
                chunk_start_char = char_position

            # Normal case: paragraph fits in chunk
            elif current_tokens + para_token_count > self.chunk_size and current_chunk:
                # Save current chunk
                chunk_text = '\n\n'.join(current_chunk)
                chunks.append(DocumentChunk(
                    content=chunk_text,
                    chunk_index=chunk_index,
                    token_count=current_tokens,
                    char_start=chunk_start_char,
                    char_end=char_position,
                    section_header=current_header
                ))
                chunk_index += 1

                # Start new chunk with overlap
                overlap_text = self._get_overlap_text(current_chunk, self.chunk_overlap)
                current_chunk = [overlap_text, para] if overlap_text else [para]
                current_tokens = len(self.encoding.encode('\n\n'.join(current_chunk)))
                chunk_start_char = char_position

            else:
                # Add to current chunk
                current_chunk.append(para)
                current_tokens += para_token_count

            char_position += len(para) + 2  # +2 for \n\n

        # Save final chunk
        if current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            chunks.append(DocumentChunk(
                content=chunk_text,
                chunk_index=chunk_index,
                token_count=current_tokens,
                char_start=chunk_start_char,
                char_end=char_position,
                section_header=current_header
            ))

        log.info(f"Chunked text into {len(chunks)} chunks (avg {sum(c.token_count for c in chunks) / len(chunks) if chunks else 0:.0f} tokens/chunk)")
        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences using basic punctuation rules"""
        import re
        # Split on . ! ? followed by space or end of string
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _get_overlap_text(self, chunks: List[str], overlap_tokens: int) -> str:
        """Get last N tokens from chunks as overlap text"""
        combined = '\n\n'.join(chunks)
        tokens = self.encoding.encode(combined)

        if len(tokens) <= overlap_tokens:
            return combined

        overlap_token_list = tokens[-overlap_tokens:]
        return self.encoding.decode(overlap_token_list)


class AzureRAGService:
    """RAG service with local chunking and Azure AI Search"""

    def __init__(self):
        if not all([AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY]):
            raise ValueError("Azure Search credentials not configured")

        if not all([AZURE_OPENAI_EMBEDDING_ENDPOINT, AZURE_OPENAI_EMBEDDING_KEY, AZURE_OPENAI_EMBEDDING_DEPLOYMENT]):
            raise ValueError("Azure OpenAI embedding credentials not configured")

        self.credential = AzureKeyCredential(AZURE_SEARCH_KEY)
        self.index_client = SearchIndexClient(
            endpoint=AZURE_SEARCH_ENDPOINT,
            credential=self.credential
        )
        self.search_client = SearchClient(
            endpoint=AZURE_SEARCH_ENDPOINT,
            index_name=AZURE_SEARCH_INDEX_NAME,
            credential=self.credential
        )

        # Initialize embedding client
        self.embedding_client = AsyncAzureOpenAI(
            azure_endpoint=AZURE_OPENAI_EMBEDDING_ENDPOINT,
            api_key=AZURE_OPENAI_EMBEDDING_KEY,
            api_version=AZURE_OPENAI_EMBEDDING_API_VERSION
        )

        # Initialize local chunker
        self.chunker = LocalChunker(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

        self._ensure_index()

    def _ensure_index(self):
        """Create or update the search index with proper schema"""
        try:
            # Try to get existing index
            existing_index = self.index_client.get_index(AZURE_SEARCH_INDEX_NAME)

            # Check if index has the correct schema (check for 'page_number' field)
            has_new_schema = any(field.name == "page_number" for field in existing_index.fields)

            if not has_new_schema:
                log.warning(f"Index {AZURE_SEARCH_INDEX_NAME} has old schema. Deleting and recreating...")
                self.index_client.delete_index(AZURE_SEARCH_INDEX_NAME)
                raise ResourceNotFoundError("Index deleted, will recreate")

            log.info(f"Using existing index: {AZURE_SEARCH_INDEX_NAME}")
        except ResourceNotFoundError:
            log.info(f"Creating new index: {AZURE_SEARCH_INDEX_NAME}")

            # Define index schema
            fields = [
                SimpleField(name="id", type=SearchFieldDataType.String, key=True),
                SimpleField(name="file_id", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="org_id", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="user_id", type=SearchFieldDataType.String, filterable=True),
                SearchableField(name="filename", type=SearchFieldDataType.String),
                SearchableField(name="content", type=SearchFieldDataType.String),
                SimpleField(name="chunk_index", type=SearchFieldDataType.Int32),
                SimpleField(name="token_count", type=SearchFieldDataType.Int32),
                SimpleField(name="page_number", type=SearchFieldDataType.Int32, filterable=True),
                SearchableField(name="section_header", type=SearchFieldDataType.String, filterable=True),
                SearchField(
                    name="content_vector",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    vector_search_dimensions=EMBEDDING_DIMENSIONS,
                    vector_search_profile_name="default-vector-profile",
                    searchable=True,
                    retrievable=True,
                    stored=True
                ),
            ]

            # Vector search configuration
            vector_search = VectorSearch(
                algorithms=[
                    HnswAlgorithmConfiguration(name="default-hnsw")
                ],
                profiles=[
                    VectorSearchProfile(
                        name="default-vector-profile",
                        algorithm_configuration_name="default-hnsw"
                    )
                ]
            )

            # Semantic search configuration
            semantic_config = SemanticConfiguration(
                name="default-semantic-config",
                prioritized_fields=SemanticPrioritizedFields(
                    content_fields=[SemanticField(field_name="content")]
                )
            )

            semantic_search = SemanticSearch(
                configurations=[semantic_config]
            )

            # Create index
            index = SearchIndex(
                name=AZURE_SEARCH_INDEX_NAME,
                fields=fields,
                vector_search=vector_search,
                semantic_search=semantic_search
            )

            self.index_client.create_index(index)
            log.info(f"Created index: {AZURE_SEARCH_INDEX_NAME}")

    async def _generate_embeddings_bulk(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts while minimizing HTTP calls."""
        if not texts:
            return []

        batch_size = max(1, EMBEDDING_BATCH_SIZE)
        embeddings: List[List[float]] = []
        log.info(
            "Generating embeddings for %d chunks (batch size: %d)",
            len(texts),
            batch_size,
        )

        for start in range(0, len(texts), batch_size):
            batch_inputs = texts[start:start + batch_size]
            attempt = 0

            while True:
                try:
                    response = await self.embedding_client.embeddings.create(
                        model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
                        input=batch_inputs
                    )

                    # Results are per-request indexed, so keep each batch ordered
                    sorted_data = sorted(
                        response.data,
                        key=lambda item: getattr(item, "index", 0)
                    )
                    embeddings.extend(item.embedding for item in sorted_data)
                    break

                except RateLimitError as e:
                    attempt += 1
                    if attempt > EMBEDDING_MAX_RETRIES:
                        log.error(
                            "Rate limited for batch starting at chunk %d and no retries left",
                            start,
                        )
                        raise

                    delay = EMBEDDING_RETRY_DELAY * attempt
                    log.warning(
                        "Rate limited while generating embeddings (batch %d-%d, attempt %d/%d). "
                        "Retrying in %.1fs",
                        start,
                        start + len(batch_inputs) - 1,
                        attempt,
                        EMBEDDING_MAX_RETRIES,
                        delay,
                    )
                    await asyncio.sleep(delay)

                except Exception as e:
                    log.error(
                        "Failed to generate embeddings for batch starting at chunk %d: %s",
                        start,
                        e,
                    )
                    raise

        return embeddings

    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text input."""
        embeddings = await self._generate_embeddings_bulk([text])
        return embeddings[0]

    async def upload_document(
        self,
        file_id: str,
        org_id: str,
        user_id: str,
        content: str,
        filename: str
    ) -> Dict[str, Any]:
        """
        Upload document with local chunking and Azure AI Search storage.

        Steps:
        1. Chunk text locally using semantic chunking
        2. Generate embeddings for each chunk
        3. Upload chunks to Azure AI Search
        """
        log.info(f"Processing document {file_id} with local chunking")

        # Step 1: Chunk text locally
        chunks = self.chunker.chunk_text(content)

        if not chunks:
            log.warning(f"No chunks generated for document {file_id}")
            return {"chunk_count": 0, "note": "No content to index"}

        # Step 2 & 3: Generate embeddings and prepare documents
        chunk_bodies = [chunk.content for chunk in chunks]
        chunk_embeddings = await self._generate_embeddings_bulk(chunk_bodies)

        if len(chunk_embeddings) != len(chunks):
            raise ValueError("Embedding count mismatch. Azure OpenAI returned fewer embeddings than requested.")

        documents = []
        for chunk, embedding in zip(chunks, chunk_embeddings):
            # Create document for Azure Search
            doc = {
                "id": f"{file_id}_{chunk.chunk_index}",
                "file_id": file_id,
                "org_id": org_id,
                "user_id": user_id,
                "filename": filename,
                "content": chunk.content,
                "chunk_index": chunk.chunk_index,
                "token_count": chunk.token_count,
                "page_number": chunk.page_number,
                "section_header": chunk.section_header,
                "content_vector": embedding
            }
            documents.append(doc)

        # Upload to Azure AI Search in batches
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            try:
                result = self.search_client.upload_documents(documents=batch)
                log.info(f"Uploaded batch {i // batch_size + 1}/{(len(documents) - 1) // batch_size + 1}")
            except Exception as e:
                log.error(f"Failed to upload batch: {e}")
                raise

        log.info(f"Successfully indexed {len(chunks)} chunks for document {file_id}")
        return {
            "chunk_count": len(chunks),
            "note": f"Indexed with local chunking ({CHUNK_SIZE} tokens, {CHUNK_OVERLAP} overlap)"
        }

    async def search_documents(
        self,
        query: str,
        org_id: str,
        user_id: str,
        file_ids: Optional[List[str]] = None,
        top_k: int = 15
    ) -> List[Dict[str, Any]]:
        """
        Search documents using vector similarity with security filtering.
        """
        import time
        start_time = time.time()

        try:
            # Generate query embedding
            log.info(f"[RAG] Starting search for query (length: {len(query)})")
            log.info(f"[RAG] Generating embedding...")
            embed_start = time.time()
            query_embedding = await self._generate_embedding(query)
            embed_time = time.time() - embed_start
            log.info(f"[RAG] Embedding generated in {embed_time:.2f}s")

            # Build filter for security and file scope
            filters = [f"org_id eq '{org_id}'", f"user_id eq '{user_id}'"]
            if file_ids:
                file_filter = " or ".join([f"file_id eq '{fid}'" for fid in file_ids])
                filters.append(f"({file_filter})")

            filter_str = " and ".join(filters)
            log.info(f"[RAG] Search filter: {filter_str}")

            # Perform vector search
            log.info(f"[RAG] Performing vector search (top_k={top_k})...")
            search_start = time.time()

            # Create vectorized query with proper kind specification
            vector_query = VectorizedQuery(
                vector=query_embedding,
                k_nearest_neighbors=top_k,
                fields="content_vector"
            )

            results = self.search_client.search(
                search_text=None,
                vector_queries=[vector_query],
                filter=filter_str,
                top=top_k,
                select=["file_id", "filename", "content", "chunk_index", "token_count", "page_number", "section_header"]
            )

            chunks = []
            for result in results:
                chunks.append({
                    "file_id": result["file_id"],
                    "filename": result["filename"],
                    "content": result["content"],
                    "chunk_index": result["chunk_index"],
                    "token_count": result["token_count"],
                    "page_number": result.get("page_number"),
                    "section_header": result.get("section_header"),
                    "score": result.get("@search.score", 0)
                })

            search_time = time.time() - search_start
            total_time = time.time() - start_time
            log.info(f"[RAG] Search completed in {search_time:.2f}s (total: {total_time:.2f}s)")
            log.info(f"[RAG] Retrieved {len(chunks)} chunks for query")
            return chunks

        except Exception as e:
            total_time = time.time() - start_time
            log.error(f"[RAG] Search failed after {total_time:.2f}s: {e}", exc_info=True)
            raise

    async def get_document_status(
        self,
        file_id: str,
        org_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Check if document is indexed"""
        try:
            filter_str = f"file_id eq '{file_id}' and org_id eq '{org_id}' and user_id eq '{user_id}'"
            results = self.search_client.search(
                search_text="*",
                filter=filter_str,
                top=1,
                include_total_count=True
            )

            # Get total count
            count = 0
            for _ in results:
                count += 1

            # Try to get actual count from the response
            try:
                results = self.search_client.search(
                    search_text="*",
                    filter=filter_str,
                    top=1000,
                    select=["id"]
                )
                count = sum(1 for _ in results)
            except:
                pass

            indexed = count > 0

            return {
                "indexed": indexed,
                "chunk_count": count,
                "note": f"Document has {count} indexed chunks" if indexed else "Document not indexed"
            }

        except Exception as e:
            log.error(f"Failed to get document status: {e}")
            return {
                "indexed": False,
                "chunk_count": 0,
                "note": f"Error checking status: {str(e)}"
            }

    async def delete_document(
        self,
        file_id: str,
        org_id: str,
        user_id: str
    ) -> None:
        """Delete all chunks for a document with security verification"""
        try:
            # Search for all chunks belonging to this document with security filter
            filter_str = f"file_id eq '{file_id}' and org_id eq '{org_id}' and user_id eq '{user_id}'"
            results = self.search_client.search(
                search_text="*",
                filter=filter_str,
                top=1000,
                select=["id"]
            )

            # Collect document IDs
            doc_ids = [{"id": result["id"]} for result in results]

            if not doc_ids:
                log.info(f"No chunks found for document {file_id}")
                return

            # Delete in batches
            batch_size = 100
            for i in range(0, len(doc_ids), batch_size):
                batch = doc_ids[i:i + batch_size]
                self.search_client.delete_documents(documents=batch)

            log.info(f"Deleted {len(doc_ids)} chunks for document {file_id}")

        except Exception as e:
            log.error(f"Failed to delete document: {e}")
            raise

    async def get_indexer_status(self) -> Dict[str, Any]:
        """Get index statistics (no indexer since we do local chunking)"""
        try:
            # Get index statistics
            results = self.search_client.search(
                search_text="*",
                top=0,
                include_total_count=True
            )

            # Count documents
            total_chunks = 0
            for _ in results:
                total_chunks += 1

            return {
                "status": "local_chunking",
                "note": "Using local chunking - no Azure indexer",
                "index_name": AZURE_SEARCH_INDEX_NAME,
                "total_chunks": total_chunks,
                "chunk_config": {
                    "chunk_size_tokens": CHUNK_SIZE,
                    "chunk_overlap_tokens": CHUNK_OVERLAP,
                    "embedding_dimensions": EMBEDDING_DIMENSIONS
                }
            }
        except Exception as e:
            log.error(f"Failed to get indexer status: {e}")
            return {
                "status": "error",
                "error": str(e)
            }


# Global singleton
_rag_service: Optional[AzureRAGService] = None


def get_rag_service() -> AzureRAGService:
    """Get or create the global RAG service instance"""
    global _rag_service
    if _rag_service is None:
        _rag_service = AzureRAGService()
    return _rag_service
