# lumen/api/app/services/azure_ocr_service.py
"""
Azure Document Intelligence OCR Service

This service uses Azure Document Intelligence (formerly Form Recognizer) to perform
OCR on scanned PDFs and images. It automatically extracts text while preserving
document layout, tables, and structure.

Features:
- Automatic OCR for scanned documents
- Multi-language support (60+ languages)
- Table and structure preservation
- High accuracy text extraction
"""

import os
import io
import logging
from typing import Optional
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError

log = logging.getLogger("lumen.ocr")

# Environment variables for Azure Document Intelligence
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
AZURE_DOCUMENT_INTELLIGENCE_KEY = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")


class AzureOCRService:
    """Service for OCR text extraction using Azure Document Intelligence"""

    def __init__(self):
        """Initialize Azure Document Intelligence client"""
        if not AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT or not AZURE_DOCUMENT_INTELLIGENCE_KEY:
            raise ValueError(
                "Azure Document Intelligence credentials not configured. "
                "Set AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and AZURE_DOCUMENT_INTELLIGENCE_KEY "
                "environment variables."
            )

        self.client = DocumentAnalysisClient(
            endpoint=AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT,
            credential=AzureKeyCredential(AZURE_DOCUMENT_INTELLIGENCE_KEY)
        )

    async def extract_text_with_ocr(self, content: bytes) -> str:
        """
        Extract text from PDF using Azure Document Intelligence OCR.

        Args:
            content: PDF file content as bytes

        Returns:
            Extracted text with preserved structure

        Raises:
            ValueError: If OCR extraction fails
        """
        try:
            log.info("Starting Azure Document Intelligence OCR processing")

            # Convert bytes to file-like object
            pdf_stream = io.BytesIO(content)

            # Use prebuilt-read model for general document OCR
            # This model is optimized for text extraction from any document type
            poller = self.client.begin_analyze_document(
                model_id="prebuilt-read",
                document=pdf_stream
            )

            # Wait for the analysis to complete
            result = poller.result()

            # Extract text from all pages
            text_parts = []

            for page in result.pages:
                # Extract lines of text from each page
                page_lines = []
                for line in page.lines:
                    page_lines.append(line.content)

                # Join lines with newlines and add page separator
                if page_lines:
                    page_text = '\n'.join(page_lines)
                    text_parts.append(page_text)

            # Join all pages with double newlines
            extracted_text = '\n\n'.join(text_parts)

            log.info(
                f"OCR extraction completed. "
                f"Pages: {len(result.pages)}, "
                f"Characters: {len(extracted_text)}"
            )

            return extracted_text

        except HttpResponseError as e:
            log.error(f"Azure Document Intelligence API error: {str(e)}")
            raise ValueError(f"OCR extraction failed: {str(e)}")
        except Exception as e:
            log.error(f"Unexpected error during OCR: {str(e)}")
            raise ValueError(f"OCR extraction failed: {str(e)}")

    @staticmethod
    def is_ocr_available() -> bool:
        """
        Check if Azure Document Intelligence OCR is properly configured.

        Returns:
            True if credentials are available, False otherwise
        """
        return bool(
            AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and
            AZURE_DOCUMENT_INTELLIGENCE_KEY
        )


# Singleton instance for reuse
_ocr_service: Optional[AzureOCRService] = None


def get_ocr_service() -> AzureOCRService:
    """
    Get or create singleton OCR service instance.

    Returns:
        AzureOCRService instance
    """
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = AzureOCRService()
    return _ocr_service
