# lumen/api/app/services/azure_ocr_service.py
"""
Azure Document Intelligence OCR Service

This service uses Azure Document Intelligence (formerly Form Recognizer) to perform
OCR on scanned PDFs and images. It uses the 'prebuilt-layout' model to extract
text while preserving document structure (tables, headers, selection marks) and
outputs Markdown content.

Features:
- Automatic OCR for scanned documents
- Layout preservation (tables, headers)
- Markdown output format
- Multi-language support
"""

import os
import logging
from typing import Optional
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult, AnalyzeDocumentRequest

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

        self.client = DocumentIntelligenceClient(
            endpoint=AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT,
            credential=AzureKeyCredential(AZURE_DOCUMENT_INTELLIGENCE_KEY)
        )

    async def extract_text_with_ocr(self, content: bytes) -> str:
        """
        Extract text from PDF using Azure Document Intelligence 'prebuilt-layout' model.
        Returns Markdown formatted text.

        Args:
            content: PDF file content as bytes

        Returns:
            Extracted text in Markdown format

        Raises:
            ValueError: If OCR extraction fails
        """
        try:
            log.info("Starting Azure Document Intelligence OCR processing (prebuilt-layout)")

            # Begin analysis
            # Note: The SDK handles the polling automatically with begin_analyze_document
            poller = self.client.begin_analyze_document(
                model_id="prebuilt-layout",
                analyze_request=AnalyzeDocumentRequest(base64_source=content),
                output_content_format="markdown"  # Request Markdown output
            )

            # Wait for the analysis to complete
            result: AnalyzeResult = poller.result()

            # Return the full markdown content
            if result.content:
                log.info(
                    f"OCR extraction completed. "
                    f"Pages: {len(result.pages) if result.pages else 0}, "
                    f"Characters: {len(result.content)}"
                )
                return result.content
            else:
                log.warning("OCR extraction returned no content.")
                return ""

        except Exception as e:
            log.error(f"Azure Document Intelligence error: {str(e)}")
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
