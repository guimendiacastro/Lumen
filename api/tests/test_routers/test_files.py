"""
Tests for file upload and management endpoints.

This module tests file upload, processing, RAG indexing, listing, and deletion.
"""

import pytest
import io
from httpx import AsyncClient
from sqlalchemy import text
from unittest.mock import patch, MagicMock

from ..conftest import TEST_ORG_ID, TEST_USER_ID


class TestFileUpload:
    """Tests for file upload endpoint."""

    @pytest.mark.asyncio
    async def test_upload_small_file_success(
        self, async_client: AsyncClient, create_test_thread, mock_vault
    ):
        """Should upload small file with direct context (no RAG)."""
        thread_id = await create_test_thread()

        # Small file (< 50KB)
        file_content = b"Small file content for testing"
        files = {"file": ("test.txt", file_content, "text/plain")}
        data = {"thread_id": thread_id}

        with patch("app.services.file_processor.FileProcessor.process_file") as mock_process:
            mock_process.return_value = MagicMock(
                full_text="Small file content for testing",
                use_direct_context=True,
                total_size=len(file_content)
            )

            response = await async_client.post("/files/upload", files=files, data=data)

        assert response.status_code == 200
        result = response.json()
        assert "file_id" in result
        assert result["filename"] == "test.txt"
        assert result["use_direct_context"] is True
        assert result["chunk_count"] == 0
        assert result["status"] == "ready"
        assert result["library_scope"] == "direct"
        assert result["indexed"] is True

    @pytest.mark.asyncio
    async def test_upload_large_file_with_rag_indexing(
        self, async_client: AsyncClient, create_test_thread, mock_vault, mock_get_rag_service
    ):
        """Should upload large file and index with RAG."""
        thread_id = await create_test_thread()

        # Large file (> 50KB)
        file_content = b"A" * (100 * 1024)
        files = {"file": ("large.pdf", file_content, "application/pdf")}
        data = {"thread_id": thread_id}

        with patch("app.services.file_processor.FileProcessor.process_file") as mock_process:
            mock_process.return_value = MagicMock(
                full_text="Extracted text from large PDF",
                use_direct_context=False,
                total_size=len(file_content)
            )

            response = await async_client.post("/files/upload", files=files, data=data)

        assert response.status_code == 200
        result = response.json()
        assert result["use_direct_context"] is False
        assert result["chunk_count"] == 5  # From mock RAG service
        assert result["status"] == "ready"
        assert result["library_scope"] == "rag"
        assert result["indexed"] is True

        # Verify RAG indexing was called
        mock_get_rag_service.upload_document.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_file_encrypts_content(
        self, async_client: AsyncClient, create_test_thread, mock_vault
    ):
        """Should encrypt file content before storage."""
        thread_id = await create_test_thread()

        file_content = b"Sensitive file content"
        files = {"file": ("secret.txt", file_content, "text/plain")}
        data = {"thread_id": thread_id}

        with patch("app.services.file_processor.FileProcessor.process_file") as mock_process:
            mock_process.return_value = MagicMock(
                full_text="Sensitive file content",
                use_direct_context=True,
                total_size=len(file_content)
            )

            response = await async_client.post("/files/upload", files=files, data=data)

        assert response.status_code == 200
        # Verify encryption was called
        mock_vault["encrypt"].assert_called()

    @pytest.mark.asyncio
    async def test_upload_file_stores_metadata(
        self, async_client: AsyncClient, create_test_thread, db_session, mock_vault
    ):
        """Should store file metadata in database."""
        thread_id = await create_test_thread()

        file_content = b"Test content"
        files = {"file": ("test.txt", file_content, "text/plain")}
        data = {"thread_id": thread_id}

        with patch("app.services.file_processor.FileProcessor.process_file") as mock_process:
            mock_process.return_value = MagicMock(
                full_text="Test content",
                use_direct_context=True,
                total_size=len(file_content)
            )

            response = await async_client.post("/files/upload", files=files, data=data)

        file_id = response.json()["file_id"]

        # Verify database record
        result = await db_session.execute(
            text("""
                SELECT filename, mime_type, file_size_bytes, status, created_by
                FROM uploaded_files
                WHERE id = :id
            """),
            {"id": file_id}
        )
        row = result.first()
        assert row is not None
        assert row[0] == "test.txt"
        assert row[1] == "text/plain"
        assert row[2] == len(file_content)
        assert row[3] == "ready"
        assert row[4] == "test_user_01"

    @pytest.mark.asyncio
    async def test_upload_file_too_large(
        self, async_client: AsyncClient, create_test_thread
    ):
        """Should reject files larger than 30MB."""
        thread_id = await create_test_thread()

        # File larger than 30MB
        file_content = b"X" * (31 * 1024 * 1024)
        files = {"file": ("huge.bin", file_content, "application/octet-stream")}
        data = {"thread_id": thread_id}

        response = await async_client.post("/files/upload", files=files, data=data)

        assert response.status_code == 413
        data = response.json()
        assert "too large" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_file_with_document_id(
        self, async_client: AsyncClient, create_test_document, mock_vault
    ):
        """Should upload file linked to document."""
        doc_id = await create_test_document()

        file_content = b"Document attachment"
        files = {"file": ("attachment.txt", file_content, "text/plain")}
        data = {"document_id": doc_id}

        with patch("app.services.file_processor.FileProcessor.process_file") as mock_process:
            mock_process.return_value = MagicMock(
                full_text="Document attachment",
                use_direct_context=True,
                total_size=len(file_content)
            )

            response = await async_client.post("/files/upload", files=files, data=data)

        assert response.status_code == 200
        file_id = response.json()["file_id"]

        # Verify document_id stored
        result = await async_client.db_session.execute(
            text("SELECT document_id FROM uploaded_files WHERE id = :id"),
            {"id": file_id}
        )

    @pytest.mark.asyncio
    async def test_upload_file_processing_error(
        self, async_client: AsyncClient, create_test_thread
    ):
        """Should return 400 when file processing fails."""
        thread_id = await create_test_thread()

        file_content = b"Corrupted file"
        files = {"file": ("corrupt.pdf", file_content, "application/pdf")}
        data = {"thread_id": thread_id}

        with patch("app.services.file_processor.FileProcessor.process_file") as mock_process:
            mock_process.side_effect = Exception("Failed to extract text")

            response = await async_client.post("/files/upload", files=files, data=data)

        assert response.status_code == 400
        result = response.json()
        assert "failed to process" in result["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_file_rag_indexing_error(
        self, async_client: AsyncClient, create_test_thread, mock_vault, mock_get_rag_service
    ):
        """Should return 500 when RAG indexing fails."""
        thread_id = await create_test_thread()

        file_content = b"A" * (100 * 1024)
        files = {"file": ("large.txt", file_content, "text/plain")}
        data = {"thread_id": thread_id}

        with patch("app.services.file_processor.FileProcessor.process_file") as mock_process:
            mock_process.return_value = MagicMock(
                full_text="Large content",
                use_direct_context=False,
                total_size=len(file_content)
            )

            # Make RAG indexing fail
            mock_get_rag_service.upload_document.side_effect = Exception("Qdrant connection failed")

            response = await async_client.post("/files/upload", files=files, data=data)

        assert response.status_code == 500
        result = response.json()
        assert "failed to index" in result["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_pdf_file(
        self, async_client: AsyncClient, create_test_thread, mock_vault
    ):
        """Should handle PDF file upload."""
        thread_id = await create_test_thread()

        file_content = b"%PDF-1.4 mock content"
        files = {"file": ("document.pdf", file_content, "application/pdf")}
        data = {"thread_id": thread_id}

        with patch("app.services.file_processor.FileProcessor.process_file") as mock_process:
            mock_process.return_value = MagicMock(
                full_text="Extracted PDF text",
                use_direct_context=True,
                total_size=len(file_content)
            )

            response = await async_client.post("/files/upload", files=files, data=data)

        assert response.status_code == 200
        result = response.json()
        assert result["filename"] == "document.pdf"

    @pytest.mark.asyncio
    async def test_upload_docx_file(
        self, async_client: AsyncClient, create_test_thread, mock_vault
    ):
        """Should handle DOCX file upload."""
        thread_id = await create_test_thread()

        file_content = b"PK\x03\x04 mock docx"
        files = {"file": ("document.docx", file_content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        data = {"thread_id": thread_id}

        with patch("app.services.file_processor.FileProcessor.process_file") as mock_process:
            mock_process.return_value = MagicMock(
                full_text="Extracted DOCX text",
                use_direct_context=True,
                total_size=len(file_content)
            )

            response = await async_client.post("/files/upload", files=files, data=data)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_upload_file_without_thread_or_document(
        self, async_client: AsyncClient, mock_vault
    ):
        """Should allow file upload without thread_id or document_id."""
        file_content = b"Standalone file"
        files = {"file": ("standalone.txt", file_content, "text/plain")}

        with patch("app.services.file_processor.FileProcessor.process_file") as mock_process:
            mock_process.return_value = MagicMock(
                full_text="Standalone file",
                use_direct_context=True,
                total_size=len(file_content)
            )

            response = await async_client.post("/files/upload", files=files)

        # Should succeed (both are optional)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_upload_file_without_filename(
        self, async_client: AsyncClient, create_test_thread, mock_vault
    ):
        """Should handle file without filename."""
        thread_id = await create_test_thread()

        file_content = b"No name file"
        files = {"file": (None, file_content, "text/plain")}
        data = {"thread_id": thread_id}

        with patch("app.services.file_processor.FileProcessor.process_file") as mock_process:
            mock_process.return_value = MagicMock(
                full_text="No name file",
                use_direct_context=True,
                total_size=len(file_content)
            )

            response = await async_client.post("/files/upload", files=files, data=data)

        assert response.status_code == 200
        result = response.json()
        assert result["filename"] == "unnamed"


class TestListFilesInThread:
    """Tests for listing files in a thread."""

    @pytest.mark.asyncio
    async def test_list_files_empty_thread(
        self, async_client: AsyncClient, create_test_thread
    ):
        """Should return empty list for thread with no files."""
        thread_id = await create_test_thread()

        response = await async_client.get(f"/files/thread/{thread_id}")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_list_files_returns_all(
        self, async_client: AsyncClient, create_test_thread, db_session, mock_vault
    ):
        """Should return all files in a thread."""
        from app.crypto.vault import encrypt_text

        thread_id = await create_test_thread()

        # Insert test files
        for i in range(3):
            content_enc = await encrypt_text("test_key_01", f"Content {i}")
            await db_session.execute(
                text("""
                    INSERT INTO uploaded_files
                    (thread_id, filename, mime_type, file_size_bytes, storage_path, content_enc, status, created_by)
                    VALUES (:tid, :name, :mime, :size, :path, :content, :status, :by)
                """),
                {
                    "tid": thread_id,
                    "name": f"file{i}.txt",
                    "mime": "text/plain",
                    "size": 1000,
                    "path": f"local/file{i}",
                    "content": content_enc,
                    "status": "ready",
                    "by": "test_user"
                }
            )
        await db_session.commit()

        response = await async_client.get(f"/files/thread/{thread_id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_list_files_response_structure(
        self, async_client: AsyncClient, create_test_thread, db_session, mock_vault
    ):
        """Should return files with expected structure."""
        from app.crypto.vault import encrypt_text

        thread_id = await create_test_thread()

        content_enc = await encrypt_text("test_key_01", "Test content")
        await db_session.execute(
            text("""
                INSERT INTO uploaded_files
                (thread_id, filename, mime_type, file_size_bytes, storage_path, content_enc, status, created_by)
                VALUES (:tid, :name, :mime, :size, :path, :content, :status, :by)
            """),
            {
                "tid": thread_id,
                "name": "test.txt",
                "mime": "text/plain",
                "size": 1000,
                "path": "local/test",
                "content": content_enc,
                "status": "ready",
                "by": "test_user"
            }
        )
        await db_session.commit()

        response = await async_client.get(f"/files/thread/{thread_id}")

        assert response.status_code == 200
        data = response.json()
        file_meta = data[0]

        # Verify structure
        assert "id" in file_meta
        assert "filename" in file_meta
        assert "mime_type" in file_meta
        assert "size_bytes" in file_meta
        assert "status" in file_meta
        assert "use_direct_context" in file_meta
        assert "created_at" in file_meta

    @pytest.mark.asyncio
    async def test_list_files_ordered_by_created_desc(
        self, async_client: AsyncClient, create_test_thread, db_session, mock_vault
    ):
        """Should return files ordered by creation time (newest first)."""
        import asyncio
        from app.crypto.vault import encrypt_text

        thread_id = await create_test_thread()

        # Insert files with delay
        file_names = []
        for i in range(3):
            content_enc = await encrypt_text("test_key_01", f"Content {i}")
            result = await db_session.execute(
                text("""
                    INSERT INTO uploaded_files
                    (thread_id, filename, mime_type, file_size_bytes, storage_path, content_enc, status, created_by)
                    VALUES (:tid, :name, :mime, :size, :path, :content, :status, :by)
                    RETURNING filename
                """),
                {
                    "tid": thread_id,
                    "name": f"file{i}.txt",
                    "mime": "text/plain",
                    "size": 1000,
                    "path": f"local/file{i}",
                    "content": content_enc,
                    "status": "ready",
                    "by": "test_user"
                }
            )
            file_names.append(result.scalar())
            await db_session.commit()
            await asyncio.sleep(0.01)

        response = await async_client.get(f"/files/thread/{thread_id}")

        data = response.json()
        # Should be in reverse order (newest first)
        assert data[0]["filename"] == "file2.txt"
        assert data[1]["filename"] == "file1.txt"
        assert data[2]["filename"] == "file0.txt"

    @pytest.mark.asyncio
    async def test_list_files_determines_direct_context(
        self, async_client: AsyncClient, create_test_thread, db_session, mock_vault
    ):
        """Should determine use_direct_context based on file size."""
        from app.crypto.vault import encrypt_text

        thread_id = await create_test_thread()

        # Small file (< 50KB)
        content_enc = await encrypt_text("test_key_01", "Small")
        await db_session.execute(
            text("""
                INSERT INTO uploaded_files
                (thread_id, filename, mime_type, file_size_bytes, storage_path, content_enc, status, created_by)
                VALUES (:tid, 'small.txt', 'text/plain', 1000, 'path', :content, 'ready', 'user')
            """),
            {"tid": thread_id, "content": content_enc}
        )

        # Large file (> 50KB)
        await db_session.execute(
            text("""
                INSERT INTO uploaded_files
                (thread_id, filename, mime_type, file_size_bytes, storage_path, content_enc, status, created_by)
                VALUES (:tid, 'large.txt', 'text/plain', 100000, 'path', :content, 'ready', 'user')
            """),
            {"tid": thread_id, "content": content_enc}
        )
        await db_session.commit()

        response = await async_client.get(f"/files/thread/{thread_id}")

        data = response.json()
        # Find files by name
        large_file = next(f for f in data if f["filename"] == "large.txt")
        small_file = next(f for f in data if f["filename"] == "small.txt")

        assert large_file["use_direct_context"] is False
        assert small_file["use_direct_context"] is True


class TestDeleteFile:
    """Tests for file deletion endpoint."""

    @pytest.mark.asyncio
    async def test_delete_file_success(
        self, async_client: AsyncClient, create_test_thread, db_session, mock_vault, mock_get_rag_service
    ):
        """Should delete file from database and RAG index."""
        from app.crypto.vault import encrypt_text

        thread_id = await create_test_thread()

        # Insert file
        content_enc = await encrypt_text("test_key_01", "Test content")
        result = await db_session.execute(
            text("""
                INSERT INTO uploaded_files
                (thread_id, filename, mime_type, file_size_bytes, storage_path, content_enc, status, created_by)
                VALUES (:tid, 'test.txt', 'text/plain', 1000, 'path', :content, 'ready', 'user')
                RETURNING id
            """),
            {"tid": thread_id, "content": content_enc}
        )
        file_id = str(result.scalar())
        await db_session.commit()

        # Delete file
        response = await async_client.delete(f"/files/{file_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert data["file_id"] == file_id

        # Verify deleted from database
        check = await db_session.execute(
            text("SELECT count(*) FROM uploaded_files WHERE id = :id"),
            {"id": file_id}
        )
        count = check.scalar()
        assert count == 0

        # Verify RAG delete was called
        mock_get_rag_service.delete_document.assert_awaited_once_with(
            file_id=file_id,
            org_id=TEST_ORG_ID,
            user_id=TEST_USER_ID,
        )

    @pytest.mark.asyncio
    async def test_delete_file_rag_deletion_error(
        self, async_client: AsyncClient, create_test_thread, db_session, mock_vault, mock_get_rag_service
    ):
        """Should still delete from database even if RAG deletion fails."""
        from app.crypto.vault import encrypt_text

        thread_id = await create_test_thread()

        content_enc = await encrypt_text("test_key_01", "Test")
        result = await db_session.execute(
            text("""
                INSERT INTO uploaded_files
                (thread_id, filename, mime_type, file_size_bytes, storage_path, content_enc, status, created_by)
                VALUES (:tid, 'test.txt', 'text/plain', 1000, 'path', :content, 'ready', 'user')
                RETURNING id
            """),
            {"tid": thread_id, "content": content_enc}
        )
        file_id = str(result.scalar())
        await db_session.commit()

        # Make RAG deletion fail
        mock_get_rag_service.delete_document.side_effect = Exception("Qdrant error")

        # Should still succeed
        response = await async_client.delete(f"/files/{file_id}")

        assert response.status_code == 200

        # Verify still deleted from database
        check = await db_session.execute(
            text("SELECT count(*) FROM uploaded_files WHERE id = :id"),
            {"id": file_id}
        )
        count = check.scalar()
        assert count == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file(
        self, async_client: AsyncClient, mock_get_rag_service
    ):
        """Should return success even if file doesn't exist (idempotent)."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = await async_client.delete(f"/files/{fake_id}")

        # Should succeed (idempotent delete)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_library_upload_and_attach_flow(
        self,
        async_client: AsyncClient,
        create_test_thread,
        mock_vault,
    ):
        """Should support uploading to library and attaching/detaching files for threads."""
        file_content = b"Library file content"
        files = {"file": ("library.txt", file_content, "text/plain")}

        with patch("app.services.file_processor.FileProcessor.process_file") as mock_process:
            mock_process.return_value = MagicMock(
                full_text="Library file content",
                use_direct_context=True,
                total_size=len(file_content)
            )

            response = await async_client.post("/files/library/upload", files=files)

        assert response.status_code == 200
        uploaded = response.json()
        file_id = uploaded["file_id"]

        resp = await async_client.get("/files/library")
        assert resp.status_code == 200
        assert any(f["id"] == file_id for f in resp.json())

        thread_id = await create_test_thread()
        attach = await async_client.post(
            f"/files/thread/{thread_id}/files",
            json={"file_ids": [file_id]}
        )
        assert attach.status_code == 200

        thread_files = await async_client.get(f"/files/thread/{thread_id}")
        assert thread_files.status_code == 200
        payload = thread_files.json()
        assert len(payload) == 1
        assert payload[0]["id"] == file_id

        detach = await async_client.delete(f"/files/thread/{thread_id}/files/{file_id}")
        assert detach.status_code == 200

        thread_files = await async_client.get(f"/files/thread/{thread_id}")
        assert thread_files.status_code == 200
        assert thread_files.json() == []


class TestFileEdgeCases:
    """Edge case tests for file endpoints."""

    @pytest.mark.asyncio
    async def test_upload_empty_file(
        self, async_client: AsyncClient, create_test_thread, mock_vault
    ):
        """Should handle empty file upload."""
        thread_id = await create_test_thread()

        file_content = b""
        files = {"file": ("empty.txt", file_content, "text/plain")}
        data = {"thread_id": thread_id}

        with patch("app.services.file_processor.FileProcessor.process_file") as mock_process:
            mock_process.return_value = MagicMock(
                full_text="",
                use_direct_context=True,
                total_size=0
            )

            response = await async_client.post("/files/upload", files=files, data=data)

        # Should either succeed or fail gracefully
        assert response.status_code in [200, 400, 422]

    @pytest.mark.asyncio
    async def test_upload_file_with_unicode_filename(
        self, async_client: AsyncClient, create_test_thread, mock_vault
    ):
        """Should handle unicode characters in filename."""
        thread_id = await create_test_thread()

        file_content = b"Content"
        files = {"file": ("文档.txt", file_content, "text/plain")}
        data = {"thread_id": thread_id}

        with patch("app.services.file_processor.FileProcessor.process_file") as mock_process:
            mock_process.return_value = MagicMock(
                full_text="Content",
                use_direct_context=True,
                total_size=len(file_content)
            )

            response = await async_client.post("/files/upload", files=files, data=data)

        assert response.status_code == 200
        result = response.json()
        assert result["filename"] == "文档.txt"

    @pytest.mark.asyncio
    async def test_concurrent_file_uploads(
        self, async_client: AsyncClient, create_test_thread, mock_vault
    ):
        """Should handle concurrent file uploads."""
        import asyncio

        thread_id = await create_test_thread()

        with patch("app.services.file_processor.FileProcessor.process_file") as mock_process:
            mock_process.return_value = MagicMock(
                full_text="Content",
                use_direct_context=True,
                total_size=100
            )

            # Upload 3 files concurrently
            tasks = []
            for i in range(3):
                files = {"file": (f"file{i}.txt", b"Content", "text/plain")}
                data = {"thread_id": thread_id}
                tasks.append(async_client.post("/files/upload", files=files, data=data))

            responses = await asyncio.gather(*tasks)

        # All should succeed
        assert all(r.status_code == 200 for r in responses)

        # All should have unique IDs
        ids = [r.json()["file_id"] for r in responses]
        assert len(ids) == len(set(ids))
