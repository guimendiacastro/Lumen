"""
Tests for FileProcessor service.

This module tests file text extraction for PDF, DOCX, and plain text files.
"""

import pytest
import io
from unittest.mock import patch, MagicMock
from app.services.file_processor import FileProcessor, FileProcessingResult


class TestPDFExtraction:
    """Tests for PDF text extraction."""

    def test_extract_text_from_pdf_success(self):
        """Should extract text from valid PDF."""
        # Mock PDF content
        mock_pdf_content = b"%PDF-1.4\ntest content"

        with patch("app.services.file_processor.PyPDF2.PdfReader") as mock_reader:
            # Mock PDF page with text
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Sample PDF text"

            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_reader.return_value = mock_pdf

            result = FileProcessor.extract_text_from_pdf(mock_pdf_content)

            assert result == "Sample PDF text"

    def test_extract_text_from_multi_page_pdf(self):
        """Should extract and combine text from multiple pages."""
        mock_pdf_content = b"%PDF test"

        with patch("app.services.file_processor.PyPDF2.PdfReader") as mock_reader:
            # Mock 3 pages
            mock_page1 = MagicMock()
            mock_page1.extract_text.return_value = "Page 1 text"

            mock_page2 = MagicMock()
            mock_page2.extract_text.return_value = "Page 2 text"

            mock_page3 = MagicMock()
            mock_page3.extract_text.return_value = "Page 3 text"

            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page1, mock_page2, mock_page3]
            mock_reader.return_value = mock_pdf

            result = FileProcessor.extract_text_from_pdf(mock_pdf_content)

            assert "Page 1 text" in result
            assert "Page 2 text" in result
            assert "Page 3 text" in result
            assert result == "Page 1 text\n\nPage 2 text\n\nPage 3 text"

    def test_extract_text_from_pdf_empty_pages(self):
        """Should handle PDF pages with no text."""
        mock_pdf_content = b"%PDF test"

        with patch("app.services.file_processor.PyPDF2.PdfReader") as mock_reader:
            mock_page1 = MagicMock()
            mock_page1.extract_text.return_value = "Page 1 text"

            mock_page2 = MagicMock()
            mock_page2.extract_text.return_value = None  # Empty page

            mock_page3 = MagicMock()
            mock_page3.extract_text.return_value = "Page 3 text"

            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page1, mock_page2, mock_page3]
            mock_reader.return_value = mock_pdf

            result = FileProcessor.extract_text_from_pdf(mock_pdf_content)

            assert "Page 1 text" in result
            assert "Page 3 text" in result

    def test_extract_text_from_corrupted_pdf(self):
        """Should raise ValueError for corrupted PDF."""
        corrupted_content = b"not a pdf"

        with patch("app.services.file_processor.PyPDF2.PdfReader") as mock_reader:
            mock_reader.side_effect = Exception("Invalid PDF")

            with pytest.raises(ValueError) as exc_info:
                FileProcessor.extract_text_from_pdf(corrupted_content)

            assert "Failed to extract text from PDF" in str(exc_info.value)


class TestDOCXExtraction:
    """Tests for DOCX text extraction."""

    def test_extract_text_from_docx_success(self):
        """Should extract text from valid DOCX."""
        mock_docx_content = b"PK\x03\x04 docx content"

        with patch("app.services.file_processor.DocxDocument") as mock_doc_class:
            # Mock paragraphs
            mock_para1 = MagicMock()
            mock_para1.text = "Paragraph 1"

            mock_para2 = MagicMock()
            mock_para2.text = "Paragraph 2"

            mock_doc = MagicMock()
            mock_doc.paragraphs = [mock_para1, mock_para2]
            mock_doc.tables = []
            mock_doc_class.return_value = mock_doc

            result = FileProcessor.extract_text_from_docx(mock_docx_content)

            assert "Paragraph 1" in result
            assert "Paragraph 2" in result

    def test_extract_text_from_docx_with_tables(self):
        """Should extract text from tables in DOCX."""
        mock_docx_content = b"PK\x03\x04 docx"

        with patch("app.services.file_processor.DocxDocument") as mock_doc_class:
            mock_doc = MagicMock()
            mock_doc.paragraphs = []

            # Mock table with 2 rows
            mock_cell1 = MagicMock()
            mock_cell1.text = "Cell1"
            mock_cell2 = MagicMock()
            mock_cell2.text = "Cell2"

            mock_row1 = MagicMock()
            mock_row1.cells = [mock_cell1, mock_cell2]

            mock_cell3 = MagicMock()
            mock_cell3.text = "Cell3"
            mock_cell4 = MagicMock()
            mock_cell4.text = "Cell4"

            mock_row2 = MagicMock()
            mock_row2.cells = [mock_cell3, mock_cell4]

            mock_table = MagicMock()
            mock_table.rows = [mock_row1, mock_row2]

            mock_doc.tables = [mock_table]
            mock_doc_class.return_value = mock_doc

            result = FileProcessor.extract_text_from_docx(mock_docx_content)

            assert "Cell1 | Cell2" in result
            assert "Cell3 | Cell4" in result

    def test_extract_text_from_docx_empty_paragraphs(self):
        """Should skip empty paragraphs."""
        mock_docx_content = b"PK\x03\x04 docx"

        with patch("app.services.file_processor.DocxDocument") as mock_doc_class:
            mock_para1 = MagicMock()
            mock_para1.text = "Paragraph 1"

            mock_para2 = MagicMock()
            mock_para2.text = "   "  # Whitespace only

            mock_para3 = MagicMock()
            mock_para3.text = "Paragraph 3"

            mock_doc = MagicMock()
            mock_doc.paragraphs = [mock_para1, mock_para2, mock_para3]
            mock_doc.tables = []
            mock_doc_class.return_value = mock_doc

            result = FileProcessor.extract_text_from_docx(mock_docx_content)

            assert "Paragraph 1" in result
            assert "Paragraph 3" in result
            # Empty paragraph should not appear
            assert result.count("\n\n") == 1  # Only one separator

    def test_extract_text_from_corrupted_docx(self):
        """Should raise ValueError for corrupted DOCX."""
        corrupted_content = b"not a docx"

        with patch("app.services.file_processor.DocxDocument") as mock_doc_class:
            mock_doc_class.side_effect = Exception("Invalid DOCX")

            with pytest.raises(ValueError) as exc_info:
                FileProcessor.extract_text_from_docx(corrupted_content)

            assert "Failed to extract text from DOCX" in str(exc_info.value)


class TestGenericTextExtraction:
    """Tests for generic file text extraction."""

    def test_extract_text_from_plain_text(self):
        """Should decode plain text files."""
        text_content = b"Plain text file content"

        result = FileProcessor.extract_text_from_file(text_content, "text/plain")

        assert result == "Plain text file content"

    def test_extract_text_from_pdf_by_mime(self):
        """Should route to PDF extractor based on mime type."""
        mock_content = b"%PDF"

        with patch.object(FileProcessor, "extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = "PDF text"

            result = FileProcessor.extract_text_from_file(mock_content, "application/pdf")

            assert result == "PDF text"
            mock_extract.assert_called_once_with(mock_content)

    def test_extract_text_from_docx_by_mime(self):
        """Should route to DOCX extractor based on mime type."""
        mock_content = b"PK\x03\x04"

        with patch.object(FileProcessor, "extract_text_from_docx") as mock_extract:
            mock_extract.return_value = "DOCX text"

            result = FileProcessor.extract_text_from_file(
                mock_content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

            assert result == "DOCX text"
            mock_extract.assert_called_once_with(mock_content)

    def test_extract_text_unsupported_binary_file(self):
        """Should raise ValueError for unsupported binary files."""
        binary_content = b"\x89PNG\r\n\x1a\n"  # PNG header

        with pytest.raises(ValueError) as exc_info:
            FileProcessor.extract_text_from_file(binary_content, "image/png")

        assert "Unsupported file type" in str(exc_info.value)

    def test_extract_text_utf8_with_bom(self):
        """Should handle UTF-8 files with BOM."""
        content_with_bom = b"\xef\xbb\xbfText with BOM"

        result = FileProcessor.extract_text_from_file(content_with_bom, "text/plain")

        assert "Text with BOM" in result


class TestFileProcessing:
    """Tests for full file processing with strategy determination."""

    def test_process_small_file_uses_direct_context(self):
        """Should use direct context for small files."""
        small_content = b"Small file content"

        with patch.object(FileProcessor, "extract_text_from_file") as mock_extract:
            mock_extract.return_value = "Small file content"

            result = FileProcessor.process_file(small_content, "text/plain")

            assert isinstance(result, FileProcessingResult)
            assert result.use_direct_context is True
            assert result.full_text == "Small file content"
            assert result.total_size == len("Small file content")

    def test_process_large_file_uses_rag(self):
        """Should use RAG for large files (> 50KB)."""
        # Create text larger than 50KB
        large_text = "X" * 60000
        large_content = large_text.encode("utf-8")

        with patch.object(FileProcessor, "extract_text_from_file") as mock_extract:
            mock_extract.return_value = large_text

            result = FileProcessor.process_file(large_content, "text/plain")

            assert isinstance(result, FileProcessingResult)
            assert result.use_direct_context is False
            assert result.total_size == 60000

    def test_process_file_at_threshold(self):
        """Should test behavior at exactly 50KB threshold."""
        # Exactly 50KB
        threshold_text = "X" * 50000
        threshold_content = threshold_text.encode("utf-8")

        with patch.object(FileProcessor, "extract_text_from_file") as mock_extract:
            mock_extract.return_value = threshold_text

            result = FileProcessor.process_file(threshold_content, "text/plain")

            # At threshold, should use direct context (<=)
            assert result.use_direct_context is True

    def test_process_file_propagates_extraction_error(self):
        """Should propagate extraction errors."""
        bad_content = b"corrupted"

        with patch.object(FileProcessor, "extract_text_from_file") as mock_extract:
            mock_extract.side_effect = ValueError("Extraction failed")

            with pytest.raises(ValueError) as exc_info:
                FileProcessor.process_file(bad_content, "bad/type")

            assert "Extraction failed" in str(exc_info.value)

    def test_process_pdf_file(self):
        """Should process PDF files correctly."""
        pdf_content = b"%PDF content"

        with patch.object(FileProcessor, "extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = "Extracted PDF text"

            result = FileProcessor.process_file(pdf_content, "application/pdf")

            assert result.use_direct_context is True
            assert result.full_text == "Extracted PDF text"

    def test_process_docx_file(self):
        """Should process DOCX files correctly."""
        docx_content = b"PK\x03\x04 docx"

        with patch.object(FileProcessor, "extract_text_from_docx") as mock_extract:
            mock_extract.return_value = "Extracted DOCX text"

            result = FileProcessor.process_file(
                docx_content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

            assert result.use_direct_context is True
            assert result.full_text == "Extracted DOCX text"


class TestEdgeCases:
    """Edge case tests for file processor."""

    def test_extract_text_from_empty_file(self):
        """Should handle empty files."""
        empty_content = b""

        result = FileProcessor.extract_text_from_file(empty_content, "text/plain")

        assert result == ""

    def test_extract_text_unicode_content(self):
        """Should handle unicode content correctly."""
        unicode_content = "Text with émojis 🎉 and 中文".encode("utf-8")

        result = FileProcessor.extract_text_from_file(unicode_content, "text/plain")

        assert "émojis 🎉" in result
        assert "中文" in result

    def test_process_file_with_only_whitespace(self):
        """Should handle files with only whitespace."""
        whitespace_content = b"   \n\n\t  \n  "

        result = FileProcessor.process_file(whitespace_content, "text/plain")

        assert result.use_direct_context is True
        assert result.full_text.strip() == ""

    def test_extract_text_case_insensitive_mime(self):
        """Should handle mime types case-insensitively."""
        content = b"%PDF"

        with patch.object(FileProcessor, "extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = "PDF text"

            # Test uppercase
            result1 = FileProcessor.extract_text_from_file(content, "APPLICATION/PDF")
            assert result1 == "PDF text"

            # Test mixed case
            result2 = FileProcessor.extract_text_from_file(content, "Application/Pdf")
            assert result2 == "PDF text"
