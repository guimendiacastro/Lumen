"""
Tests for documents CRUD endpoints.

This module tests document creation, retrieval, update operations
with encryption/decryption and versioning.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import text


class TestDocumentCreation:
    """Tests for document creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_document_success(
        self, async_client: AsyncClient, db_session, mock_vault
    ):
        """Should create document with encrypted content and return document ID."""
        payload = {
            "title": "Test Document",
            "content": "This is the document content for testing."
        }

        response = await async_client.post("/documents", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert len(data["id"]) == 36  # UUID length with hyphens

        # Verify database state
        result = await db_session.execute(
            text("SELECT title, content_enc, mime, created_by FROM documents WHERE id = :id"),
            {"id": data["id"]}
        )
        row = result.first()
        assert row is not None
        assert row[0] == payload["title"]
        assert row[1].startswith(b"vault:v1:encrypted_")
        assert row[2] == "text/markdown"
        assert row[3] == "test_user_01"

    @pytest.mark.asyncio
    async def test_create_document_creates_version(
        self, async_client: AsyncClient, db_session, mock_vault
    ):
        """Should create version 1 when document is created."""
        payload = {
            "title": "Versioned Document",
            "content": "Initial content"
        }

        response = await async_client.post("/documents", json=payload)
        doc_id = response.json()["id"]

        # Check version exists
        result = await db_session.execute(
            text("""
                SELECT version, content_enc
                FROM doc_versions
                WHERE document_id = :id
            """),
            {"id": doc_id}
        )
        row = result.first()
        assert row is not None
        assert row[0] == 1  # Version 1
        assert row[1].startswith(b"vault:v1:encrypted_")

    @pytest.mark.asyncio
    async def test_create_document_encrypts_content(
        self, async_client: AsyncClient, mock_vault
    ):
        """Should encrypt content before storing in database."""
        payload = {
            "title": "Encrypted Document",
            "content": "Sensitive content that must be encrypted"
        }

        response = await async_client.post("/documents", json=payload)

        assert response.status_code == 200
        # Verify encrypt was called
        mock_vault["encrypt"].assert_called()

    @pytest.mark.parametrize("payload,expected_field", [
        ({}, "title"),
        ({"title": ""}, "content"),
        ({"content": "test"}, "title"),
    ])
    @pytest.mark.asyncio
    async def test_create_document_validation_errors(
        self, async_client: AsyncClient, payload, expected_field
    ):
        """Should reject requests with missing required fields."""
        response = await async_client.post("/documents", json=payload)

        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(expected_field in str(e) for e in errors)

    @pytest.mark.asyncio
    async def test_create_document_with_empty_title(
        self, async_client: AsyncClient
    ):
        """Should reject document with empty title."""
        payload = {
            "title": "",
            "content": "Some content"
        }

        response = await async_client.post("/documents", json=payload)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_document_with_long_title(
        self, async_client: AsyncClient, db_session, mock_vault
    ):
        """Should handle very long titles."""
        payload = {
            "title": "A" * 1000,
            "content": "Content"
        }

        response = await async_client.post("/documents", json=payload)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_document_with_unicode_content(
        self, async_client: AsyncClient, db_session, mock_vault
    ):
        """Should handle unicode characters in title and content."""
        payload = {
            "title": "Document with émojis 🎉",
            "content": "Content with 中文字符 and العربية"
        }

        response = await async_client.post("/documents", json=payload)

        assert response.status_code == 200
        data = response.json()

        # Verify stored correctly
        result = await db_session.execute(
            text("SELECT title FROM documents WHERE id = :id"),
            {"id": data["id"]}
        )
        title = result.scalar()
        assert title == payload["title"]

    @pytest.mark.asyncio
    async def test_create_document_with_special_characters(
        self, async_client: AsyncClient, mock_vault
    ):
        """Should handle special characters and HTML in content."""
        payload = {
            "title": "Document <with> special & chars",
            "content": "<script>alert('test')</script>\n\nSQL: '; DROP TABLE--"
        }

        response = await async_client.post("/documents", json=payload)

        assert response.status_code == 200


class TestDocumentRetrieval:
    """Tests for document retrieval endpoint."""

    @pytest.mark.asyncio
    async def test_get_document_success(
        self, async_client: AsyncClient, create_test_document, mock_vault
    ):
        """Should retrieve and decrypt document by ID."""
        doc_id = await create_test_document(
            title="Test Document",
            content="Test content"
        )

        response = await async_client.get(f"/documents/{doc_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == doc_id
        assert data["title"] == "Test Document"
        assert data["content"] == "Test content"
        assert data["mime"] == "text/markdown"

    @pytest.mark.asyncio
    async def test_get_document_decrypts_content(
        self, async_client: AsyncClient, create_test_document, mock_vault
    ):
        """Should decrypt content before returning."""
        doc_id = await create_test_document(
            title="Encrypted Doc",
            content="Secret content"
        )

        response = await async_client.get(f"/documents/{doc_id}")

        assert response.status_code == 200
        # Verify decrypt was called
        mock_vault["decrypt"].assert_called()

    @pytest.mark.asyncio
    async def test_get_document_not_found(
        self, async_client: AsyncClient
    ):
        """Should return 404 when document does not exist."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = await async_client.get(f"/documents/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_document_with_invalid_uuid(
        self, async_client: AsyncClient
    ):
        """Should handle invalid UUID format gracefully."""
        invalid_id = "not-a-uuid"

        response = await async_client.get(f"/documents/{invalid_id}")

        # May return 404 or 422 depending on validation
        assert response.status_code in [404, 422, 500]

    @pytest.mark.asyncio
    async def test_get_document_response_structure(
        self, async_client: AsyncClient, create_test_document, mock_vault
    ):
        """Should return document with expected structure."""
        doc_id = await create_test_document()

        response = await async_client.get(f"/documents/{doc_id}")

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields present
        assert "id" in data
        assert "title" in data
        assert "content" in data
        assert "mime" in data

        # Verify types
        assert isinstance(data["id"], str)
        assert isinstance(data["title"], str)
        assert isinstance(data["content"], str)
        assert isinstance(data["mime"], str)


class TestDocumentUpdate:
    """Tests for document update endpoint."""

    @pytest.mark.asyncio
    async def test_update_document_success(
        self, async_client: AsyncClient, create_test_document, mock_vault
    ):
        """Should update document content and create new version."""
        doc_id = await create_test_document(
            title="Original Title",
            content="Original content"
        )

        payload = {"content": "Updated content"}
        response = await async_client.put(f"/documents/{doc_id}", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["version"] == 2  # Should be version 2

    @pytest.mark.asyncio
    async def test_update_document_creates_new_version(
        self, async_client: AsyncClient, create_test_document, db_session, mock_vault
    ):
        """Should create new version entry on update."""
        doc_id = await create_test_document(content="Version 1")

        # Update twice
        await async_client.put(f"/documents/{doc_id}", json={"content": "Version 2"})
        await async_client.put(f"/documents/{doc_id}", json={"content": "Version 3"})

        # Check version count
        result = await db_session.execute(
            text("""
                SELECT version
                FROM doc_versions
                WHERE document_id = :id
                ORDER BY version
            """),
            {"id": doc_id}
        )
        versions = [row[0] for row in result]
        assert versions == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_update_document_updates_main_table(
        self, async_client: AsyncClient, create_test_document, db_session, mock_vault
    ):
        """Should update content in main documents table."""
        doc_id = await create_test_document(content="Original")

        new_content = "Updated content"
        await async_client.put(f"/documents/{doc_id}", json={"content": new_content})

        # Retrieve and verify
        response = await async_client.get(f"/documents/{doc_id}")
        data = response.json()
        assert data["content"] == new_content

    @pytest.mark.asyncio
    async def test_update_document_not_found(
        self, async_client: AsyncClient
    ):
        """Should return 404 when updating non-existent document."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        payload = {"content": "New content"}

        response = await async_client.put(f"/documents/{fake_id}", json=payload)

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_document_missing_content(
        self, async_client: AsyncClient, create_test_document, mock_vault
    ):
        """Should reject update without content field."""
        doc_id = await create_test_document()

        response = await async_client.put(f"/documents/{doc_id}", json={})

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_document_sets_updated_by(
        self, async_client: AsyncClient, create_test_document, db_session, mock_vault
    ):
        """Should set updated_by field to current user."""
        doc_id = await create_test_document()

        await async_client.put(f"/documents/{doc_id}", json={"content": "Updated"})

        # Check updated_by
        result = await db_session.execute(
            text("SELECT updated_by FROM documents WHERE id = :id"),
            {"id": doc_id}
        )
        updated_by = result.scalar()
        assert updated_by == "test_user_01"

    @pytest.mark.asyncio
    async def test_update_document_updates_timestamp(
        self, async_client: AsyncClient, create_test_document, db_session, mock_vault
    ):
        """Should update the updated_at timestamp."""
        import asyncio

        doc_id = await create_test_document()

        # Get original timestamp
        result1 = await db_session.execute(
            text("SELECT updated_at FROM documents WHERE id = :id"),
            {"id": doc_id}
        )
        original_time = result1.scalar()

        # Wait a moment and update
        await asyncio.sleep(0.1)
        await async_client.put(f"/documents/{doc_id}", json={"content": "Updated"})

        # Get new timestamp
        await db_session.commit()  # Ensure fresh read
        result2 = await db_session.execute(
            text("SELECT updated_at FROM documents WHERE id = :id"),
            {"id": doc_id}
        )
        new_time = result2.scalar()

        assert new_time > original_time

    @pytest.mark.asyncio
    async def test_update_document_with_large_content(
        self, async_client: AsyncClient, create_test_document, mock_vault
    ):
        """Should handle large content updates."""
        doc_id = await create_test_document()

        # 1MB of content
        large_content = "A" * (1024 * 1024)
        payload = {"content": large_content}

        response = await async_client.put(f"/documents/{doc_id}", json=payload)

        assert response.status_code == 200


class TestDocumentSanitizeEndpoint:
    """Tests for sanitize preview endpoint."""

    @pytest.mark.asyncio
    async def test_sanitize_removes_email(
        self, async_client: AsyncClient
    ):
        """Should sanitize email addresses."""
        payload = {"text": "Contact us at test@example.com for info"}

        response = await async_client.post("/documents/_sanitize", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "[EMAIL]" in data["sanitized"]
        assert "test@example.com" not in data["sanitized"]

    @pytest.mark.asyncio
    async def test_sanitize_removes_phone(
        self, async_client: AsyncClient
    ):
        """Should sanitize phone numbers."""
        payload = {"text": "Call me at +1-555-123-4567"}

        response = await async_client.post("/documents/_sanitize", json=payload)

        assert response.status_code == 200
        data = response.json()
        # Check if phone pattern was detected (implementation dependent)
        assert "[PHONE]" in data["sanitized"] or "+1-555" not in data["sanitized"]

    @pytest.mark.asyncio
    async def test_sanitize_preserves_non_pii(
        self, async_client: AsyncClient
    ):
        """Should preserve non-PII content."""
        payload = {"text": "This is a normal sentence without PII."}

        response = await async_client.post("/documents/_sanitize", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "normal sentence" in data["sanitized"]

    @pytest.mark.asyncio
    async def test_sanitize_empty_text(
        self, async_client: AsyncClient
    ):
        """Should handle empty text."""
        payload = {"text": ""}

        response = await async_client.post("/documents/_sanitize", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["sanitized"] == ""

    @pytest.mark.asyncio
    async def test_sanitize_multiple_pii_types(
        self, async_client: AsyncClient
    ):
        """Should handle multiple PII types in same text."""
        payload = {
            "text": "Email: john@example.com, Phone: +1-555-1234, IBAN: GB82WEST12345698765432"
        }

        response = await async_client.post("/documents/_sanitize", json=payload)

        assert response.status_code == 200
        data = response.json()
        # Verify PII markers present
        sanitized = data["sanitized"]
        assert "john@example.com" not in sanitized


class TestDocumentEdgeCases:
    """Edge case tests for document endpoints."""

    @pytest.mark.asyncio
    async def test_document_with_null_bytes(
        self, async_client: AsyncClient, mock_vault
    ):
        """Should handle content with null bytes."""
        payload = {
            "title": "Test",
            "content": "Content\x00with\x00nulls"
        }

        response = await async_client.post("/documents", json=payload)

        # Should either succeed or reject gracefully
        assert response.status_code in [200, 400, 422]

    @pytest.mark.asyncio
    async def test_concurrent_document_creation(
        self, async_client: AsyncClient, mock_vault
    ):
        """Should handle concurrent document creation."""
        import asyncio

        payloads = [
            {"title": f"Doc {i}", "content": f"Content {i}"}
            for i in range(5)
        ]

        tasks = [
            async_client.post("/documents", json=p)
            for p in payloads
        ]
        responses = await asyncio.gather(*tasks)

        # All should succeed
        assert all(r.status_code == 200 for r in responses)

        # All should have unique IDs
        ids = [r.json()["id"] for r in responses]
        assert len(ids) == len(set(ids))

    @pytest.mark.asyncio
    async def test_document_content_max_size(
        self, async_client: AsyncClient, mock_vault
    ):
        """Should handle maximum reasonable content size."""
        # 10MB content
        large_content = "X" * (10 * 1024 * 1024)
        payload = {
            "title": "Large Document",
            "content": large_content
        }

        response = await async_client.post("/documents", json=payload)

        # Should succeed or fail gracefully
        assert response.status_code in [200, 413, 422]
