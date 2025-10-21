# lumen/api/app/services/rag_service.py


import os
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

from llama_index.core import VectorStoreIndex, Document, StorageContext, Settings
from llama_index.core.node_parser import SentenceWindowNodeParser
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

log = logging.getLogger("lumen.ai")

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))


@dataclass
class RetrievedChunk:
    """Represents a retrieved chunk with metadata"""
    text: str
    score: float
    metadata: Dict
    chunk_id: str


class RAGService:
    """
    Modern RAG service using LlamaIndex and Qdrant.
    Handles document indexing and retrieval.
    """
    
    def __init__(self):
        """Initialize RAG service with LlamaIndex and Qdrant"""
        log.info("Initializing RAG Service...")
        
        # Initialize Qdrant client
        self.qdrant_client = QdrantClient(
            host=QDRANT_HOST,
            port=QDRANT_PORT,
            timeout=60
        )
        log.info(f"Connected to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
        
        # Initialize embedding model
        embed_model = HuggingFaceEmbedding(
            model_name=EMBEDDING_MODEL,
            cache_folder="./model_cache"
        )
        log.info(f"Loaded embedding model: {EMBEDDING_MODEL}")
        
        # Configure LlamaIndex settings globally
        Settings.embed_model = embed_model
        Settings.chunk_size = CHUNK_SIZE
        Settings.chunk_overlap = CHUNK_OVERLAP
        
        # Setup node parser for better chunking
        self.node_parser = SentenceWindowNodeParser.from_defaults(
            window_size=3,  # Include 3 sentences of context
            window_metadata_key="window",
            original_text_metadata_key="original_text",
        )
        
        log.info("RAG Service initialized successfully")
    
    def _get_collection_name(self, file_id: str) -> str:
        """Generate collection name for a file"""
        return f"file_{file_id}"
    
    def _ensure_collection(self, collection_name: str, vector_size: int = 1024):
        """Ensure Qdrant collection exists"""
        collections = self.qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if collection_name not in collection_names:
            self.qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE
                )
            )
            log.info(f"Created Qdrant collection: {collection_name}")
    
    async def index_document(
        self,
        file_id: str,
        text: str,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Index a document with LlamaIndex.
        
        Args:
            file_id: Unique file identifier
            text: Full document text
            metadata: Optional metadata dict
            
        Returns:
            Number of chunks created
        """
        log.info(f"Indexing document {file_id}...")
        
        collection_name = self._get_collection_name(file_id)
        self._ensure_collection(collection_name)
        
        # Create LlamaIndex document
        doc_metadata = metadata or {}
        doc_metadata["file_id"] = file_id
        
        document = Document(
            text=text,
            id_=file_id,
            metadata=doc_metadata
        )
        
        # Create vector store
        vector_store = QdrantVectorStore(
            client=self.qdrant_client,
            collection_name=collection_name
        )
        
        storage_context = StorageContext.from_defaults(
            vector_store=vector_store
        )
        
        # Index with sentence window chunking
        index = VectorStoreIndex.from_documents(
            [document],
            storage_context=storage_context,
            node_parser=self.node_parser,
            show_progress=False
        )
        
        # Count chunks
        chunk_count = len(index.docstore.docs)
        log.info(f"Indexed {chunk_count} chunks for file {file_id}")
        
        return chunk_count
    
    async def retrieve(
        self,
        file_id: str,
        query: str,
        top_k: int = 15,
        min_score: float = 0.5
    ) -> List[RetrievedChunk]:
        """
        Retrieve relevant chunks for a query.
        
        Args:
            file_id: File identifier to search in
            query: Search query
            top_k: Number of chunks to retrieve
            min_score: Minimum similarity score
            
        Returns:
            List of retrieved chunks with scores
        """
        log.info(f"Retrieving chunks for query: {query[:100]}...")
        
        collection_name = self._get_collection_name(file_id)
        
        # Check if collection exists
        collections = self.qdrant_client.get_collections().collections
        if collection_name not in [c.name for c in collections]:
            log.warning(f"Collection {collection_name} not found")
            return []
        
        # Create vector store
        vector_store = QdrantVectorStore(
            client=self.qdrant_client,
            collection_name=collection_name
        )
        
        # Load index
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store
        )
        
        # Create retriever
        retriever = index.as_retriever(
            similarity_top_k=top_k
        )
        
        # Retrieve nodes
        nodes = retriever.retrieve(query)
        
        # Convert to our format and filter by score
        chunks = []
        for node in nodes:
            if node.score >= min_score:
                chunks.append(RetrievedChunk(
                    text=node.node.get_content(),
                    score=node.score,
                    metadata=node.node.metadata,
                    chunk_id=node.node.node_id
                ))
        
        log.info(f"Retrieved {len(chunks)} chunks above threshold {min_score}")
        return chunks
    
    async def retrieve_from_multiple_files(
        self,
        file_ids: List[str],
        query: str,
        top_k_per_file: int = 5,
        min_score: float = 0.5
    ) -> List[RetrievedChunk]:
        """
        Retrieve from multiple files and merge results.
        
        Args:
            file_ids: List of file identifiers
            query: Search query
            top_k_per_file: Chunks to retrieve per file
            min_score: Minimum similarity score
            
        Returns:
            Merged list of retrieved chunks, sorted by score
        """
        all_chunks = []
        
        for file_id in file_ids:
            try:
                chunks = await self.retrieve(
                    file_id=file_id,
                    query=query,
                    top_k=top_k_per_file,
                    min_score=min_score
                )
                all_chunks.extend(chunks)
            except Exception as e:
                log.error(f"Error retrieving from file {file_id}: {e}")
                continue
        
        # Sort by score descending
        all_chunks.sort(key=lambda x: x.score, reverse=True)
        
        return all_chunks
    
    async def delete_file_index(self, file_id: str):
        """Delete a file's index from Qdrant"""
        collection_name = self._get_collection_name(file_id)
        
        try:
            self.qdrant_client.delete_collection(collection_name)
            log.info(f"Deleted collection: {collection_name}")
        except Exception as e:
            log.warning(f"Could not delete collection {collection_name}: {e}")


# Global instance
_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Get or create global RAG service instance"""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service