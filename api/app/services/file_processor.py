# lumen/api/app/services/file_processor.py
"""
Simplified file processor - only handles text extraction
Chunking and embeddings are now handled by RAGService
"""

import io
from typing import Optional
from dataclasses import dataclass

import PyPDF2
from docx import Document as DocxDocument

MAX_DIRECT_CONTEXT_CHARS = 50000


@dataclass
class FileProcessingResult:
    """Result of file processing."""
    use_direct_context: bool
    full_text: str
    total_size: int


class FileProcessor:
    """Simplified file processor - only extracts text"""
    
    @staticmethod
    def extract_text_from_pdf(content: bytes) -> str:
        """Extract text from PDF using PyPDF2."""
        try:
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
            doc_file = io.BytesIO(content)
            doc = DocxDocument(doc_file)
            
            text_parts = []
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text_parts.append(paragraph.text)
            
            # Also extract text from tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = ' | '.join(cell.text for cell in row.cells)
                    if row_text.strip():
                        text_parts.append(row_text)
            
            return '\n\n'.join(text_parts)
        except Exception as e:
            raise ValueError(f"Failed to extract text from DOCX: {str(e)}")
    
    @staticmethod
    def extract_text_from_file(content: bytes, mime_type: str) -> str:
        """Extract text from file based on mime type"""
        if 'pdf' in mime_type.lower():
            return FileProcessor.extract_text_from_pdf(content)
        elif 'word' in mime_type.lower() or 'docx' in mime_type.lower():
            return FileProcessor.extract_text_from_docx(content)
        else:
            # Try decoding as text
            try:
                return content.decode('utf-8')
            except UnicodeDecodeError:
                raise ValueError(f"Unsupported file type: {mime_type}")
    
    @staticmethod
    def process_file(content: bytes, mime_type: str) -> FileProcessingResult:
        """
        Process file and determine if direct context or RAG should be used.
        """
        # Extract text
        text = FileProcessor.extract_text_from_file(content, mime_type)
        text_size = len(text)
        
        # Decide strategy based on size
        use_direct = text_size <= MAX_DIRECT_CONTEXT_CHARS
        
        return FileProcessingResult(
            use_direct_context=use_direct,
            full_text=text,
            total_size=text_size
        )