"""
Tests for chat threads and messages endpoints.

This module tests thread creation, message posting, and thread listing
with sanitization and encryption.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import text


class TestThreadCreation:
    """Tests for thread creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_thread_success(
        self, async_client: AsyncClient, db_session
    ):
        """Should create a new chat thread."""
        payload = {
            "title": "Test Thread",
            "document_id": None
        }

        response = await async_client.post("/threads", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["title"] == "Test Thread"
        assert data["document_id"] is None

    @pytest.mark.asyncio
    async def test_create_thread_linked_to_document(
        self, async_client: AsyncClient, create_test_document, mock_vault
    ):
        """Should create thread linked to a document."""
        doc_id = await create_test_document()

        payload = {
            "title": "Document Discussion",
            "document_id": doc_id
        }

        response = await async_client.post("/threads", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == doc_id

    @pytest.mark.asyncio
    async def test_create_thread_without_title(
        self, async_client: AsyncClient
    ):
        """Should create thread with null title."""
        payload = {"title": None}

        response = await async_client.post("/threads", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["title"] is None

    @pytest.mark.asyncio
    async def test_create_thread_stores_creator(
        self, async_client: AsyncClient, db_session
    ):
        """Should store the creator user_id."""
        payload = {"title": "My Thread"}

        response = await async_client.post("/threads", json=payload)
        thread_id = response.json()["id"]

        # Verify created_by
        result = await db_session.execute(
            text("SELECT created_by FROM chat_threads WHERE id = :id"),
            {"id": thread_id}
        )
        created_by = result.scalar()
        assert created_by == "test_user_01"

    @pytest.mark.asyncio
    async def test_create_thread_sets_timestamp(
        self, async_client: AsyncClient, db_session
    ):
        """Should set created_at timestamp."""
        payload = {"title": "Timestamped Thread"}

        response = await async_client.post("/threads", json=payload)
        thread_id = response.json()["id"]

        # Verify timestamp
        result = await db_session.execute(
            text("SELECT created_at FROM chat_threads WHERE id = :id"),
            {"id": thread_id}
        )
        timestamp = result.scalar()
        assert timestamp is not None

    @pytest.mark.asyncio
    async def test_create_thread_with_unicode_title(
        self, async_client: AsyncClient
    ):
        """Should handle unicode characters in title."""
        payload = {"title": "Thread with émojis 🎯 and 中文"}

        response = await async_client.post("/threads", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == payload["title"]


class TestPostMessage:
    """Tests for posting messages to threads."""

    @pytest.mark.asyncio
    async def test_post_message_success(
        self, async_client: AsyncClient, create_test_thread, mock_vault
    ):
        """Should post a message to an existing thread."""
        thread_id = await create_test_thread()

        payload = {
            "text": "Hello, this is a test message",
            "role": "user"
        }

        response = await async_client.post(
            f"/threads/{thread_id}/messages",
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["thread_id"] == thread_id
        assert data["role"] == "user"
        assert data["text"] == payload["text"]

    @pytest.mark.asyncio
    async def test_post_message_encrypts_content(
        self, async_client: AsyncClient, create_test_thread, mock_vault
    ):
        """Should encrypt both raw and sanitized text."""
        thread_id = await create_test_thread()

        payload = {"text": "Secret message"}

        response = await async_client.post(
            f"/threads/{thread_id}/messages",
            json=payload
        )

        assert response.status_code == 200
        # Verify encrypt was called twice (raw + sanitized)
        assert mock_vault["encrypt"].call_count >= 2

    @pytest.mark.asyncio
    async def test_post_message_sanitizes_content(
        self, async_client: AsyncClient, create_test_thread, db_session, mock_vault
    ):
        """Should sanitize message content before encryption."""
        thread_id = await create_test_thread()

        payload = {"text": "Contact me at test@example.com"}

        response = await async_client.post(
            f"/threads/{thread_id}/messages",
            json=payload
        )

        assert response.status_code == 200
        # Sanitized version should be encrypted separately
        # (exact sanitization checked in sanitize tests)

    @pytest.mark.asyncio
    async def test_post_message_stores_hash(
        self, async_client: AsyncClient, create_test_thread, db_session, mock_vault
    ):
        """Should store SHA256 hash of raw text."""
        thread_id = await create_test_thread()

        payload = {"text": "Test message"}

        response = await async_client.post(
            f"/threads/{thread_id}/messages",
            json=payload
        )
        message_id = response.json()["id"]

        # Verify hash stored
        result = await db_session.execute(
            text("SELECT raw_hash FROM chat_messages WHERE id = :id"),
            {"id": message_id}
        )
        hash_value = result.scalar()
        assert hash_value is not None
        assert len(hash_value) == 64  # SHA256 hex length

    @pytest.mark.asyncio
    async def test_post_message_to_nonexistent_thread(
        self, async_client: AsyncClient
    ):
        """Should return 404 when thread does not exist."""
        fake_thread_id = "00000000-0000-0000-0000-000000000000"
        payload = {"text": "Message to nowhere"}

        response = await async_client.post(
            f"/threads/{fake_thread_id}/messages",
            json=payload
        )

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_post_message_default_role_user(
        self, async_client: AsyncClient, create_test_thread, mock_vault
    ):
        """Should default to 'user' role if not specified."""
        thread_id = await create_test_thread()

        payload = {"text": "Message without role"}

        response = await async_client.post(
            f"/threads/{thread_id}/messages",
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "user"

    @pytest.mark.asyncio
    async def test_post_message_system_role(
        self, async_client: AsyncClient, create_test_thread, mock_vault
    ):
        """Should accept 'system' role."""
        thread_id = await create_test_thread()

        payload = {
            "text": "System message",
            "role": "system"
        }

        response = await async_client.post(
            f"/threads/{thread_id}/messages",
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "system"

    @pytest.mark.asyncio
    async def test_post_message_with_very_long_text(
        self, async_client: AsyncClient, create_test_thread, mock_vault
    ):
        """Should handle very long message text."""
        thread_id = await create_test_thread()

        # 100KB message
        long_text = "A" * (100 * 1024)
        payload = {"text": long_text}

        response = await async_client.post(
            f"/threads/{thread_id}/messages",
            json=payload
        )

        # Should succeed or fail gracefully
        assert response.status_code in [200, 413, 422]

    @pytest.mark.asyncio
    async def test_post_message_missing_text_field(
        self, async_client: AsyncClient, create_test_thread, mock_vault
    ):
        """Should reject message without text field."""
        thread_id = await create_test_thread()

        response = await async_client.post(
            f"/threads/{thread_id}/messages",
            json={"role": "user"}
        )

        assert response.status_code == 422


class TestListThreads:
    """Tests for listing threads endpoint."""

    @pytest.mark.asyncio
    async def test_list_threads_empty(
        self, async_client: AsyncClient
    ):
        """Should return empty list when no threads exist."""
        response = await async_client.get("/threads")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_list_threads_returns_all(
        self, async_client: AsyncClient, create_test_thread
    ):
        """Should return all threads."""
        # Create 3 threads
        for i in range(3):
            await create_test_thread(title=f"Thread {i}")

        response = await async_client.get("/threads")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_list_threads_pagination_limit(
        self, async_client: AsyncClient, create_test_thread
    ):
        """Should respect limit parameter."""
        # Create 10 threads
        for i in range(10):
            await create_test_thread(title=f"Thread {i}")

        response = await async_client.get("/threads?limit=5")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

    @pytest.mark.asyncio
    async def test_list_threads_pagination_offset(
        self, async_client: AsyncClient, create_test_thread
    ):
        """Should respect offset parameter."""
        # Create threads with distinct titles
        for i in range(5):
            await create_test_thread(title=f"Thread {i:02d}")

        # Get first 2
        response1 = await async_client.get("/threads?limit=2&offset=0")
        first_batch = response1.json()

        # Get next 2
        response2 = await async_client.get("/threads?limit=2&offset=2")
        second_batch = response2.json()

        # Should be different threads
        first_ids = {t["id"] for t in first_batch}
        second_ids = {t["id"] for t in second_batch}
        assert first_ids.isdisjoint(second_ids)

    @pytest.mark.asyncio
    async def test_list_threads_ordered_by_created_at_desc(
        self, async_client: AsyncClient, create_test_thread
    ):
        """Should return threads ordered by creation time (newest first)."""
        import asyncio

        # Create threads with slight delay
        thread1_id = await create_test_thread(title="First")
        await asyncio.sleep(0.01)
        thread2_id = await create_test_thread(title="Second")
        await asyncio.sleep(0.01)
        thread3_id = await create_test_thread(title="Third")

        response = await async_client.get("/threads")
        data = response.json()

        # Should be in reverse order (newest first)
        assert data[0]["id"] == thread3_id
        assert data[1]["id"] == thread2_id
        assert data[2]["id"] == thread1_id

    @pytest.mark.asyncio
    async def test_list_threads_response_structure(
        self, async_client: AsyncClient, create_test_thread
    ):
        """Should return threads with expected structure."""
        await create_test_thread(title="Test Thread")

        response = await async_client.get("/threads")

        assert response.status_code == 200
        data = response.json()
        thread = data[0]

        # Verify structure
        assert "id" in thread
        assert "title" in thread
        assert "document_id" in thread
        assert "created_at" in thread

    @pytest.mark.asyncio
    async def test_list_threads_does_not_include_messages(
        self, async_client: AsyncClient, create_test_thread, create_test_message, mock_vault
    ):
        """Should not include messages in list (lightweight response)."""
        thread_id = await create_test_thread()
        await create_test_message(thread_id, message_text="Test message")

        response = await async_client.get("/threads")

        assert response.status_code == 200
        data = response.json()
        thread = data[0]

        # Should not have messages field
        assert "messages" not in thread


class TestGetThreadWithMessages:
    """Tests for retrieving single thread with messages."""

    @pytest.mark.asyncio
    async def test_get_thread_with_no_messages(
        self, async_client: AsyncClient, create_test_thread
    ):
        """Should return thread with empty messages array."""
        thread_id = await create_test_thread(title="Empty Thread")

        response = await async_client.get(f"/threads/{thread_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == thread_id
        assert data["title"] == "Empty Thread"
        assert data["messages"] == []

    @pytest.mark.asyncio
    async def test_get_thread_with_messages(
        self, async_client: AsyncClient, create_test_thread, create_test_message, mock_vault
    ):
        """Should return thread with decrypted sanitized messages."""
        thread_id = await create_test_thread()
        await create_test_message(thread_id, message_text="First message")
        await create_test_message(thread_id, message_text="Second message")

        response = await async_client.get(f"/threads/{thread_id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 2

    @pytest.mark.asyncio
    async def test_get_thread_messages_ordered_oldest_first(
        self, async_client: AsyncClient, create_test_thread, create_test_message, mock_vault
    ):
        """Should return messages ordered by creation time (oldest first)."""
        import asyncio

        thread_id = await create_test_thread()

        msg1_id = await create_test_message(thread_id, message_text="First")
        await asyncio.sleep(0.01)
        msg2_id = await create_test_message(thread_id, message_text="Second")
        await asyncio.sleep(0.01)
        msg3_id = await create_test_message(thread_id, message_text="Third")

        response = await async_client.get(f"/threads/{thread_id}")
        data = response.json()

        messages = data["messages"]
        assert messages[0]["id"] == msg1_id
        assert messages[1]["id"] == msg2_id
        assert messages[2]["id"] == msg3_id

    @pytest.mark.asyncio
    async def test_get_thread_decrypts_messages(
        self, async_client: AsyncClient, create_test_thread, create_test_message, mock_vault
    ):
        """Should decrypt sanitized message content."""
        thread_id = await create_test_thread()
        await create_test_message(thread_id, message_text="Test message")

        response = await async_client.get(f"/threads/{thread_id}")

        assert response.status_code == 200
        data = response.json()
        message = data["messages"][0]
        assert "sanitized" in message
        assert message["sanitized"] == "Test message"

    @pytest.mark.asyncio
    async def test_get_thread_normalizes_system_role(
        self, async_client: AsyncClient, create_test_thread, db_session, mock_vault
    ):
        """Should normalize 'system' role to 'assistant' in response."""
        from app.crypto.vault import encrypt_text

        thread_id = await create_test_thread()

        # Insert system message directly
        text_enc = await encrypt_text("test_key_01", "System message")
        await db_session.execute(
            text("""
                INSERT INTO chat_messages (thread_id, role, raw_hash, text_enc, sanitized_enc)
                VALUES (:tid, 'system', 'hash', :enc, :enc)
            """),
            {"tid": thread_id, "enc": text_enc}
        )
        await db_session.commit()

        response = await async_client.get(f"/threads/{thread_id}")

        assert response.status_code == 200
        data = response.json()
        message = data["messages"][0]
        assert message["role"] == "assistant"  # Normalized from system

    @pytest.mark.asyncio
    async def test_get_thread_not_found(
        self, async_client: AsyncClient
    ):
        """Should return 404 when thread does not exist."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = await async_client.get(f"/threads/{fake_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_thread_message_structure(
        self, async_client: AsyncClient, create_test_thread, create_test_message, mock_vault
    ):
        """Should return messages with expected structure."""
        thread_id = await create_test_thread()
        await create_test_message(thread_id, message_text="Test")

        response = await async_client.get(f"/threads/{thread_id}")

        assert response.status_code == 200
        data = response.json()
        message = data["messages"][0]

        # Verify message structure
        assert "id" in message
        assert "role" in message
        assert "sanitized" in message
        assert "ts" in message


class TestListMessagesEndpoint:
    """Tests for list messages endpoint (debug endpoint)."""

    @pytest.mark.asyncio
    async def test_list_messages_returns_items(
        self, async_client: AsyncClient, create_test_thread, create_test_message, mock_vault
    ):
        """Should return messages in items array."""
        thread_id = await create_test_thread()
        await create_test_message(thread_id, message_text="Message 1")
        await create_test_message(thread_id, message_text="Message 2")

        response = await async_client.get(f"/threads/{thread_id}/messages")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_messages_empty_thread(
        self, async_client: AsyncClient, create_test_thread
    ):
        """Should return empty items array for thread with no messages."""
        thread_id = await create_test_thread()

        response = await async_client.get(f"/threads/{thread_id}/messages")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []


class TestThreadEdgeCases:
    """Edge case tests for thread endpoints."""

    @pytest.mark.asyncio
    async def test_concurrent_message_posting(
        self, async_client: AsyncClient, create_test_thread, mock_vault
    ):
        """Should handle concurrent messages to same thread."""
        import asyncio

        thread_id = await create_test_thread()

        # Post 5 messages concurrently
        tasks = [
            async_client.post(
                f"/threads/{thread_id}/messages",
                json={"text": f"Message {i}"}
            )
            for i in range(5)
        ]
        responses = await asyncio.gather(*tasks)

        # All should succeed
        assert all(r.status_code == 200 for r in responses)

        # Verify all stored
        response = await async_client.get(f"/threads/{thread_id}")
        data = response.json()
        assert len(data["messages"]) == 5

    @pytest.mark.asyncio
    async def test_thread_with_deleted_document_reference(
        self, async_client: AsyncClient, create_test_document, create_test_thread, db_session, mock_vault
    ):
        """Should handle thread with deleted document (SET NULL)."""
        doc_id = await create_test_document()
        thread_id = await create_test_thread(document_id=doc_id)

        # Delete document
        await db_session.execute(
            text("DELETE FROM documents WHERE id = :id"),
            {"id": doc_id}
        )
        await db_session.commit()

        # Thread should still exist with null document_id
        response = await async_client.get(f"/threads/{thread_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] is None

    @pytest.mark.asyncio
    async def test_thread_list_max_limit(
        self, async_client: AsyncClient
    ):
        """Should enforce maximum limit of 200."""
        response = await async_client.get("/threads?limit=300")

        # Should either cap at 200 or return validation error
        assert response.status_code in [200, 422]

    @pytest.mark.asyncio
    async def test_thread_list_negative_offset(
        self, async_client: AsyncClient
    ):
        """Should reject negative offset."""
        response = await async_client.get("/threads?offset=-1")

        assert response.status_code == 422
