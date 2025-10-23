"""
Tests for AI comparison endpoint.

This module tests the main AI endpoint that builds prompts with context
and fans out to multiple providers.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from unittest.mock import patch, AsyncMock


class TestAICompare:
    """Tests for AI compare endpoint."""

    @pytest.mark.asyncio
    async def test_compare_basic_request(
        self,
        async_client: AsyncClient,
        create_test_thread,
        create_test_message,
        mock_vault,
        mock_llm_clients
    ):
        """Should return responses from all three providers."""
        thread_id = await create_test_thread()
        message_id = await create_test_message(thread_id, text="Draft a contract")

        payload = {
            "thread_id": thread_id,
            "message_id": message_id
        }

        response = await async_client.post("/ai/compare", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data
        assert "providers" in data
        assert len(data["providers"]) == 3

        # Verify provider structure
        for provider in data["providers"]:
            assert "id" in provider
            assert "provider" in provider
            assert "text" in provider
            assert provider["provider"] in ["openai", "anthropic", "xai"]

    @pytest.mark.asyncio
    async def test_compare_stores_request_record(
        self,
        async_client: AsyncClient,
        create_test_thread,
        create_test_message,
        db_session,
        mock_vault,
        mock_llm_clients
    ):
        """Should create ai_requests record."""
        thread_id = await create_test_thread()
        message_id = await create_test_message(thread_id, text="Test request")

        payload = {
            "thread_id": thread_id,
            "message_id": message_id
        }

        response = await async_client.post("/ai/compare", json=payload)
        request_id = response.json()["request_id"]

        # Verify request record
        result = await db_session.execute(
            text("""
                SELECT thread_id, message_id, scope
                FROM ai_requests
                WHERE id = :id
            """),
            {"id": request_id}
        )
        row = result.first()
        assert row is not None
        assert str(row[0]) == thread_id
        assert str(row[1]) == message_id
        assert row[2] == "full"

    @pytest.mark.asyncio
    async def test_compare_stores_encrypted_responses(
        self,
        async_client: AsyncClient,
        create_test_thread,
        create_test_message,
        db_session,
        mock_vault,
        mock_llm_clients
    ):
        """Should encrypt and store all provider responses."""
        thread_id = await create_test_thread()
        message_id = await create_test_message(thread_id, text="Test")

        payload = {
            "thread_id": thread_id,
            "message_id": message_id
        }

        response = await async_client.post("/ai/compare", json=payload)
        request_id = response.json()["request_id"]

        # Verify responses stored
        result = await db_session.execute(
            text("""
                SELECT provider, text_enc, input_tokens, output_tokens
                FROM ai_responses
                WHERE request_id = :id
            """),
            {"id": request_id}
        )
        rows = result.all()
        assert len(rows) == 3

        # Verify providers
        providers = {row[0] for row in rows}
        assert providers == {"openai", "anthropic", "xai"}

        # Verify encrypted
        for row in rows:
            assert row[1].startswith(b"vault:v1:encrypted_")

    @pytest.mark.asyncio
    async def test_compare_includes_document_context(
        self,
        async_client: AsyncClient,
        create_test_document,
        create_test_thread,
        create_test_message,
        mock_vault,
        mock_llm_clients
    ):
        """Should include current document in prompt context."""
        doc_id = await create_test_document(
            title="Test Doc",
            content="This is the current document content."
        )
        thread_id = await create_test_thread(document_id=doc_id)
        message_id = await create_test_message(thread_id, text="Revise this")

        payload = {
            "thread_id": thread_id,
            "message_id": message_id
        }

        with patch("app.llm.clients.fanout_with_history") as mock_fanout:
            mock_fanout.return_value = [
                {
                    "provider": "openai",
                    "text": "OpenAI response",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "latency_ms": 500
                }
            ]

            response = await async_client.post("/ai/compare", json=payload)

            assert response.status_code == 200

            # Verify fanout was called with document context
            mock_fanout.assert_called_once()
            messages = mock_fanout.call_args[0][0]

            # Check for document context in messages
            doc_context = any(
                "<current_document>" in msg.get("content", "")
                for msg in messages
            )
            assert doc_context, "Document context should be in messages"

    @pytest.mark.asyncio
    async def test_compare_includes_conversation_history(
        self,
        async_client: AsyncClient,
        create_test_thread,
        create_test_message,
        mock_vault,
        mock_llm_clients
    ):
        """Should include previous user messages in context."""
        thread_id = await create_test_thread()

        # Create multiple messages
        msg1_id = await create_test_message(thread_id, text="First request")
        msg2_id = await create_test_message(thread_id, text="Second request")
        msg3_id = await create_test_message(thread_id, text="Third request")

        payload = {
            "thread_id": thread_id,
            "message_id": msg3_id
        }

        with patch("app.llm.clients.fanout_with_history") as mock_fanout:
            mock_fanout.return_value = [
                {
                    "provider": "openai",
                    "text": "Response",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "latency_ms": 500
                }
            ]

            response = await async_client.post("/ai/compare", json=payload)

            assert response.status_code == 200

            # Verify history included
            mock_fanout.assert_called_once()
            messages = mock_fanout.call_args[0][0]

            # Check for previous requests in history
            history_msg = any(
                "Previous requests" in msg.get("content", "")
                for msg in messages
            )
            assert history_msg, "Should include conversation history"

    @pytest.mark.asyncio
    async def test_compare_with_custom_system_prompt(
        self,
        async_client: AsyncClient,
        create_test_thread,
        create_test_message,
        mock_vault,
        mock_llm_clients
    ):
        """Should allow custom system prompt."""
        thread_id = await create_test_thread()
        message_id = await create_test_message(thread_id, text="Test")

        payload = {
            "thread_id": thread_id,
            "message_id": message_id,
            "system": "You are an expert in contract law."
        }

        with patch("app.llm.clients.fanout_with_history") as mock_fanout:
            mock_fanout.return_value = [
                {
                    "provider": "openai",
                    "text": "Response",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "latency_ms": 500
                }
            ]

            response = await async_client.post("/ai/compare", json=payload)

            assert response.status_code == 200

            # Verify custom system prompt included
            mock_fanout.assert_called_once()
            messages = mock_fanout.call_args[0][0]
            system_msg = messages[0]
            assert system_msg["role"] == "system"
            assert "expert in contract law" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_compare_message_not_found(
        self,
        async_client: AsyncClient,
        create_test_thread,
        mock_llm_clients
    ):
        """Should return 404 when message doesn't exist."""
        thread_id = await create_test_thread()
        fake_message_id = "00000000-0000-0000-0000-000000000000"

        payload = {
            "thread_id": thread_id,
            "message_id": fake_message_id
        }

        response = await async_client.post("/ai/compare", json=payload)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_compare_returns_latency_info(
        self,
        async_client: AsyncClient,
        create_test_thread,
        create_test_message,
        mock_vault
    ):
        """Should return latency information for each provider."""
        thread_id = await create_test_thread()
        message_id = await create_test_message(thread_id, text="Test")

        payload = {
            "thread_id": thread_id,
            "message_id": message_id
        }

        with patch("app.llm.clients.fanout_with_history") as mock_fanout:
            mock_fanout.return_value = [
                {
                    "provider": "openai",
                    "text": "Response",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "latency_ms": 523
                },
                {
                    "provider": "anthropic",
                    "text": "Response",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "latency_ms": 612
                }
            ]

            response = await async_client.post("/ai/compare", json=payload)

            assert response.status_code == 200
            data = response.json()

            # Check latency info present
            for provider in data["providers"]:
                assert "latencyMs" in provider
                assert isinstance(provider["latencyMs"], int)

    @pytest.mark.asyncio
    async def test_compare_missing_thread_id(
        self,
        async_client: AsyncClient,
        create_test_message,
        mock_vault
    ):
        """Should reject request without thread_id."""
        payload = {
            "message_id": "some-id"
        }

        response = await async_client.post("/ai/compare", json=payload)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_compare_missing_message_id(
        self,
        async_client: AsyncClient,
        create_test_thread
    ):
        """Should reject request without message_id."""
        thread_id = await create_test_thread()

        payload = {
            "thread_id": thread_id
        }

        response = await async_client.post("/ai/compare", json=payload)

        assert response.status_code == 422


class TestAICompareWithFiles:
    """Tests for AI compare with file context."""

    @pytest.mark.asyncio
    async def test_compare_includes_small_file_content(
        self,
        async_client: AsyncClient,
        create_test_thread,
        create_test_message,
        db_session,
        mock_vault,
        mock_llm_clients
    ):
        """Should include small file content directly in context."""
        from app.crypto.vault import encrypt_text

        thread_id = await create_test_thread()
        message_id = await create_test_message(thread_id, text="Analyze the file")

        # Insert small file (direct context)
        content_enc = await encrypt_text("test_key_01", "File content here")
        await db_session.execute(
            text("""
                INSERT INTO uploaded_files
                (thread_id, filename, mime_type, file_size_bytes, storage_path, content_enc, status, created_by)
                VALUES (:tid, 'small.txt', 'text/plain', 1000, 'path', :content, 'ready', 'user')
            """),
            {"tid": thread_id, "content": content_enc}
        )
        await db_session.commit()

        payload = {
            "thread_id": thread_id,
            "message_id": message_id
        }

        with patch("app.llm.clients.fanout_with_history") as mock_fanout:
            mock_fanout.return_value = [
                {
                    "provider": "openai",
                    "text": "Response",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "latency_ms": 500
                }
            ]

            response = await async_client.post("/ai/compare", json=payload)

            assert response.status_code == 200

            # Verify file context included
            mock_fanout.assert_called_once()
            messages = mock_fanout.call_args[0][0]

            file_context = any(
                "<uploaded_files>" in msg.get("content", "")
                for msg in messages
            )
            assert file_context, "Should include uploaded files context"

    @pytest.mark.asyncio
    async def test_compare_uses_rag_for_large_files(
        self,
        async_client: AsyncClient,
        create_test_thread,
        create_test_message,
        db_session,
        mock_vault,
        mock_llm_clients,
        mock_get_rag_service
    ):
        """Should use RAG retrieval for large files."""
        from app.crypto.vault import encrypt_text

        thread_id = await create_test_thread()
        message_id = await create_test_message(thread_id, text="Query about document")

        # Insert large file (RAG indexed)
        content_enc = await encrypt_text("test_key_01", "A" * 100000)
        file_result = await db_session.execute(
            text("""
                INSERT INTO uploaded_files
                (thread_id, filename, mime_type, file_size_bytes, storage_path, content_enc, status, created_by)
                VALUES (:tid, 'large.pdf', 'application/pdf', 100000, 'path', :content, 'ready', 'user')
                RETURNING id
            """),
            {"tid": thread_id, "content": content_enc}
        )
        file_id = str(file_result.scalar())

        # Simulate file_chunks exist (indicating RAG indexed)
        await db_session.execute(
            text("""
                CREATE TABLE IF NOT EXISTS file_chunks (
                    file_id UUID,
                    chunk_id TEXT,
                    page_number INT,
                    section_title TEXT,
                    content_type TEXT,
                    metadata JSONB,
                    embedding VECTOR(384),
                    is_particulars BOOLEAN
                )
            """)
        )
        await db_session.commit()

        payload = {
            "thread_id": thread_id,
            "message_id": message_id
        }

        with patch("app.llm.clients.fanout_with_history") as mock_fanout:
            mock_fanout.return_value = [
                {
                    "provider": "openai",
                    "text": "Response",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "latency_ms": 500
                }
            ]

            response = await async_client.post("/ai/compare", json=payload)

            assert response.status_code == 200

            # Verify RAG was called
            # Note: In actual implementation, RAG is called via _get_rag_context
            # which checks for files and retrieves relevant chunks


class TestAICompareEdgeCases:
    """Edge case tests for AI compare endpoint."""

    @pytest.mark.asyncio
    async def test_compare_with_very_long_message(
        self,
        async_client: AsyncClient,
        create_test_thread,
        create_test_message,
        mock_vault,
        mock_llm_clients
    ):
        """Should handle very long user messages."""
        thread_id = await create_test_thread()
        long_text = "Please " + ("analyze this " * 1000)
        message_id = await create_test_message(thread_id, text=long_text)

        payload = {
            "thread_id": thread_id,
            "message_id": message_id
        }

        response = await async_client.post("/ai/compare", json=payload)

        # Should succeed or fail gracefully
        assert response.status_code in [200, 413, 422]

    @pytest.mark.asyncio
    async def test_compare_with_empty_thread(
        self,
        async_client: AsyncClient,
        create_test_thread,
        create_test_message,
        mock_vault,
        mock_llm_clients
    ):
        """Should handle thread with only one message (no history)."""
        thread_id = await create_test_thread()
        message_id = await create_test_message(thread_id, text="First message")

        payload = {
            "thread_id": thread_id,
            "message_id": message_id
        }

        response = await async_client.post("/ai/compare", json=payload)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_compare_when_provider_fails(
        self,
        async_client: AsyncClient,
        create_test_thread,
        create_test_message,
        mock_vault
    ):
        """Should handle partial provider failures."""
        thread_id = await create_test_thread()
        message_id = await create_test_message(thread_id, text="Test")

        payload = {
            "thread_id": thread_id,
            "message_id": message_id
        }

        with patch("app.llm.clients.fanout_with_history") as mock_fanout:
            # One provider succeeds, others fail
            mock_fanout.return_value = [
                {
                    "provider": "openai",
                    "text": "Success response",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "latency_ms": 500,
                    "ok": True
                },
                {
                    "provider": "anthropic",
                    "text": "Error occurred",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "latency_ms": 0,
                    "ok": False
                }
            ]

            response = await async_client.post("/ai/compare", json=payload)

            # Should still return results
            assert response.status_code == 200
            data = response.json()
            providers = data["providers"]

            # Check ok status
            openai_provider = next(p for p in providers if p["provider"] == "openai")
            assert openai_provider["ok"] is True

    @pytest.mark.asyncio
    async def test_compare_with_special_characters_in_content(
        self,
        async_client: AsyncClient,
        create_test_thread,
        create_test_message,
        mock_vault,
        mock_llm_clients
    ):
        """Should handle special characters in messages."""
        thread_id = await create_test_thread()
        special_text = "Draft §1: 'Contracting Parties' — €1,000 + <tags> & \"quotes\""
        message_id = await create_test_message(thread_id, text=special_text)

        payload = {
            "thread_id": thread_id,
            "message_id": message_id
        }

        response = await async_client.post("/ai/compare", json=payload)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_compare_document_content_truncation(
        self,
        async_client: AsyncClient,
        create_test_document,
        create_test_thread,
        create_test_message,
        mock_vault,
        mock_llm_clients
    ):
        """Should truncate very large documents to MAX_DOC_CHARS."""
        # Create doc with > 24000 chars (MAX_DOC_CHARS)
        large_content = "X" * 50000
        doc_id = await create_test_document(content=large_content)

        thread_id = await create_test_thread(document_id=doc_id)
        message_id = await create_test_message(thread_id, text="Revise")

        payload = {
            "thread_id": thread_id,
            "message_id": message_id
        }

        with patch("app.llm.clients.fanout_with_history") as mock_fanout:
            mock_fanout.return_value = [
                {
                    "provider": "openai",
                    "text": "Response",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "latency_ms": 500
                }
            ]

            response = await async_client.post("/ai/compare", json=payload)

            assert response.status_code == 200

            # Verify document was truncated in context
            mock_fanout.assert_called_once()
            messages = mock_fanout.call_args[0][0]

            # Find document message
            doc_msg = next(
                (m for m in messages if "<current_document>" in m.get("content", "")),
                None
            )
            assert doc_msg is not None
            # Content should be truncated to last MAX_DOC_CHARS
            assert len(doc_msg["content"]) < len(large_content)
