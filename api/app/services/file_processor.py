# lumen/api/app/services/file_processor.py
"""
File processing service with chunking and embedding strategies.
Supports both direct context (small files) and RAG (large files).
Now includes PDF and DOCX extraction.
"""

import os
import re
import hashlib
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import httpx
from dotenv import load_dotenv

# PDF and DOCX processing
import PyPDF2
from docx import Document as DocxDocument

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MAX_DIRECT_CONTEXT_CHARS = 50000  # ~12k tokens, safe for direct context
CHUNK_SIZE_CHARS = 1000  # Target chunk size
CHUNK_OVERLAP_CHARS = 200  # Overlap between chunks


@dataclass
class ProcessedChunk:
    """Represents a single chunk of text."""
    text: str
    chunk_type: str
    token_count: int
    metadata: Dict


@dataclass
class FileProcessingResult:
    """Result of file processing."""
    use_direct_context: bool  # True if small enough for direct context
    full_text: Optional[str]  # If using direct context
    chunks: List[ProcessedChunk]  # If using RAG
    total_size: int


class FileProcessor:
    """Processes files for either direct context or RAG."""
    
    @staticmethod
    def extract_text_from_pdf(content: bytes) -> str:
        """Extract text from PDF using PyPDF2."""
        try:
            import io
            pdf_file = io.BytesIO(content)
            reader = PyPDF2.PdfReader(pdf_file)
            
            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            
            return '\n\n'.join(text_parts)
        except Exception as e:
            raise ValueError(f"Failed to extract text from PDF: {str(e)}")
    
    @staticmethod
    def extract_text_from_docx(content: bytes) -> str:
        """Extract text from DOCX using python-docx."""
        try:
            import io
            docx_file = io.BytesIO(content)
            doc = DocxDocument(docx_file)
            
            text_parts = []
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text_parts.append(paragraph.text)
            
            # Also extract text from tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = ' | '.join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_text:
                        text_parts.append(row_text)
            
            return '\n\n'.join(text_parts)
        except Exception as e:
            raise ValueError(f"Failed to extract text from DOCX: {str(e)}")
    
    @staticmethod
    def extract_text_from_file(content: bytes, mime_type: str) -> str:
        """
        Extract text from various file types.
        Supports: TXT, MD, PDF, DOCX, DOC
        """
        if mime_type.startswith('text/'):
            return content.decode('utf-8', errors='ignore')
        
        elif mime_type == 'application/pdf':
            return FileProcessor.extract_text_from_pdf(content)
        
        elif mime_type in [
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # .docx
            'application/msword'  # .doc (older format)
        ]:
            return FileProcessor.extract_text_from_docx(content)
        
        else:
            # Try UTF-8 decode as fallback
            try:
                return content.decode('utf-8', errors='ignore')
            except Exception:
                raise ValueError(f"Unsupported file type: {mime_type}")
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token estimation: ~4 chars per token."""
        return len(text) // 4
    
    @staticmethod
    def semantic_chunking(text: str) -> List[ProcessedChunk]:
        """
        Semantic chunking: splits on paragraph boundaries with overlap.
        Best for preserving context in documents.
        """
        # Split on double newlines (paragraphs)
        paragraphs = re.split(r'\n\s*\n', text)
        
        chunks = []
        current_chunk = ""
        chunk_idx = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # If adding this paragraph exceeds chunk size, start new chunk
            if len(current_chunk) + len(para) > CHUNK_SIZE_CHARS and current_chunk:
                chunks.append(ProcessedChunk(
                    text=current_chunk,
                    chunk_type='semantic',
                    token_count=FileProcessor.estimate_tokens(current_chunk),
                    metadata={'chunk_index': chunk_idx, 'method': 'semantic'}
                ))
                
                # Start new chunk with overlap
                words = current_chunk.split()
                overlap = ' '.join(words[-50:]) if len(words) > 50 else current_chunk
                current_chunk = overlap + "\n\n" + para
                chunk_idx += 1
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
        
        # Add final chunk
        if current_chunk:
            chunks.append(ProcessedChunk(
                text=current_chunk,
                chunk_type='semantic',
                token_count=FileProcessor.estimate_tokens(current_chunk),
                metadata={'chunk_index': chunk_idx, 'method': 'semantic'}
            ))
        
        return chunks
    
    @staticmethod
    def fixed_size_chunking(text: str) -> List[ProcessedChunk]:
        """
        Fixed-size chunking with overlap.
        Good for homogeneous text without clear structure.
        """
        chunks = []
        start = 0
        chunk_idx = 0
        
        while start < len(text):
            end = start + CHUNK_SIZE_CHARS
            chunk_text = text[start:end]
            
            # Try to break at sentence boundary
            if end < len(text):
                last_period = chunk_text.rfind('. ')
                if last_period > CHUNK_SIZE_CHARS * 0.7:  # Only if > 70% through
                    end = start + last_period + 2
                    chunk_text = text[start:end]
            
            chunks.append(ProcessedChunk(
                text=chunk_text,
                chunk_type='fixed_size',
                token_count=FileProcessor.estimate_tokens(chunk_text),
                metadata={'chunk_index': chunk_idx, 'start': start, 'end': end}
            ))
            
            # Move to next chunk with overlap
            start = end - CHUNK_OVERLAP_CHARS
            chunk_idx += 1
        
        return chunks
    
    @staticmethod
    def process_file(content: bytes, mime_type: str) -> FileProcessingResult:
        """
        Main entry point: decide strategy and process file.
        """
        # Extract text
        text = FileProcessor.extract_text_from_file(content, mime_type)
        text_size = len(text)
        
        # Decide strategy based on size
        use_direct = text_size <= MAX_DIRECT_CONTEXT_CHARS
        
        if use_direct:
            # Small file: use direct context
            return FileProcessingResult(
                use_direct_context=True,
                full_text=text,
                chunks=[],
                total_size=text_size
            )
        else:
            # Large file: chunk for RAG
            # Use semantic chunking by default (better quality)
            chunks = FileProcessor.semantic_chunking(text)
            
            return FileProcessingResult(
                use_direct_context=False,
                full_text=None,
                chunks=chunks,
                total_size=text_size
            )


class EmbeddingService:
    """Generates vector embeddings for text chunks."""
    
    def __init__(self, model: str = "text-embedding-3-small"):
        self.model = model
        self.api_key = OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")
    
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts using OpenAI API.
        Batches up to 100 at a time for efficiency.
        """
        if not texts:
            return []
        
        embeddings = []
        batch_size = 100
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "input": batch,
                        "model": self.model
                    }
                )
                response.raise_for_status()
                
                data = response.json()
                batch_embeddings = [item["embedding"] for item in data["data"]]
                embeddings.extend(batch_embeddings)
        
        return embeddings
    
    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)


class RAGRetriever:
    """Retrieves relevant chunks for a query using vector similarity."""
    
    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service
    
    async def retrieve_relevant_chunks(
        self,
        query: str,
        chunk_embeddings: List[Tuple[str, List[float]]],  # (chunk_text, embedding)
        top_k: int = 5,
        min_similarity: float = 0.3
    ) -> List[Tuple[str, float]]:
        """
        Retrieve top-k most relevant chunks for a query.
        Returns list of (chunk_text, similarity_score).
        """
        # Generate query embedding
        query_embeddings = await self.embedding_service.generate_embeddings([query])
        query_embedding = query_embeddings[0]
        
        # Compute similarities
        similarities = []
        for chunk_text, chunk_embedding in chunk_embeddings:
            similarity = EmbeddingService.cosine_similarity(query_embedding, chunk_embedding)
            if similarity >= min_similarity:
                similarities.append((chunk_text, similarity))
        
        # Sort by similarity and return top-k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]