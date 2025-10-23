"""
Shared pytest fixtures for LUMEN API tests.

This module provides core fixtures for:
- Database setup with test schema and transaction rollback
- HTTP client with FastAPI app integration
- Authentication mocking (Identity override)
- Vault encryption/decryption mocking
- RAG service mocking
"""

import os
import pytest
import pytest_asyncio
from typing import AsyncIterator
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from contextlib import asynccontextmanager

# Import app components
from app.main import app
from app.security import get_identity, Identity
from app.db import member_session

# Test configuration
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/lumen_test"
)
TEST_SCHEMA_NAME = "test_mem_01"
TEST_ORG_ID = "test_org_01"
TEST_USER_ID = "test_user_01"
TEST_VAULT_KEY = "test_key_01"


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """
    Create test database engine and initialize schema.

    This fixture:
    1. Creates async engine for test database
    2. Creates control.members table
    3. Creates test member schema with all tables
    4. Yields engine for test session
    5. Cleans up test schema after all tests
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        pool_pre_ping=True,
        echo=False,
    )

    async with engine.begin() as conn:
        # Create control schema and members table
        await conn.execute(text("""
            CREATE SCHEMA IF NOT EXISTS control
        """))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS control.members (
                org_id TEXT PRIMARY KEY,
                schema_name TEXT NOT NULL UNIQUE,
                vault_key_id TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # Insert test organization
        await conn.execute(text("""
            INSERT INTO control.members (org_id, schema_name, vault_key_id)
            VALUES (:org_id, :schema_name, :vault_key_id)
            ON CONFLICT (org_id) DO UPDATE SET
                schema_name = EXCLUDED.schema_name,
                vault_key_id = EXCLUDED.vault_key_id
        """), {
            "org_id": TEST_ORG_ID,
            "schema_name": TEST_SCHEMA_NAME,
            "vault_key_id": TEST_VAULT_KEY
        })

        # Create test member schema
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {TEST_SCHEMA_NAME}"))

        # Set search path and create tables
        await conn.execute(text(f"SET search_path TO {TEST_SCHEMA_NAME}, public"))

        # Documents table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                title TEXT NOT NULL,
                content_enc BYTEA NOT NULL,
                mime TEXT DEFAULT 'text/markdown',
                created_by TEXT NOT NULL,
                updated_by TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # Document versions table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS doc_versions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                version INT NOT NULL,
                content_enc BYTEA NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(document_id, version)
            )
        """))

        # Chat threads table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chat_threads (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
                title TEXT,
                created_by TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # Chat messages table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                thread_id UUID NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                raw_hash TEXT,
                text_enc BYTEA NOT NULL,
                sanitized_enc BYTEA,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # AI requests table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                thread_id UUID NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
                message_id UUID NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
                scope TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # AI responses table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_responses (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                request_id UUID NOT NULL REFERENCES ai_requests(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                text_enc BYTEA NOT NULL,
                input_tokens INT,
                output_tokens INT,
                latency_ms INT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # AI selections table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_selections (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                request_id UUID NOT NULL REFERENCES ai_requests(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                selection_meta JSONB,
                applied_to_document UUID REFERENCES documents(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # Uploaded files table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS uploaded_files (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
                thread_id UUID REFERENCES chat_threads(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                mime_type TEXT,
                file_size_bytes BIGINT,
                storage_path TEXT,
                content_enc BYTEA NOT NULL,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
                error_message TEXT,
                created_by TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                processed_at TIMESTAMPTZ
            )
        """))

        # Audit logs table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT,
                details JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # Thread summaries table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS thread_summaries (
                thread_id UUID PRIMARY KEY REFERENCES chat_threads(id) ON DELETE CASCADE,
                summary_enc BYTEA NOT NULL,
                version INT DEFAULT 1,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # Memory facts table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS memory_facts (
                fact_hash TEXT PRIMARY KEY,
                fact_enc BYTEA NOT NULL,
                source TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

    yield engine

    # Cleanup: Drop test schema after all tests
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA_NAME} CASCADE"))

    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def db_session(test_engine) -> AsyncIterator[AsyncSession]:
    """
    Create a database session with transaction rollback.

    This fixture:
    1. Creates a connection from the engine
    2. Begins a transaction
    3. Creates an async session
    4. Sets search_path to test schema
    5. Yields session for test
    6. Rolls back transaction after test (no permanent changes)

    The autouse=True makes this run for every test automatically.
    """
    async with test_engine.connect() as conn:
        # Begin transaction
        trans = await conn.begin()

        # Create session bound to this connection
        AsyncSessionLocal = async_sessionmaker(
            bind=conn,
            expire_on_commit=False,
        )

        async with AsyncSessionLocal() as session:
            # Set search path to test schema
            await session.execute(text(f"SET LOCAL search_path TO {TEST_SCHEMA_NAME}, public"))

            # Patch member_session to return this session
            @asynccontextmanager
            async def mock_member_session(schema_name: str):
                yield session

            with patch("app.db.member_session", mock_member_session):
                # Patch fetch_member_mapping to return test schema
                async def mock_fetch_member_mapping(org_id: str):
                    if org_id == TEST_ORG_ID:
                        return {
                            "schema_name": TEST_SCHEMA_NAME,
                            "vault_key_id": TEST_VAULT_KEY
                        }
                    return None

                with patch("app.db.fetch_member_mapping", mock_fetch_member_mapping):
                    yield session

            # Rollback transaction (all changes discarded)
            await trans.rollback()


# ============================================================================
# Authentication Fixtures
# ============================================================================

@pytest.fixture
def test_identity() -> Identity:
    """Return a test Identity object."""
    return Identity(user_id=TEST_USER_ID, org_id=TEST_ORG_ID)


@pytest.fixture
def override_get_identity(test_identity):
    """Override the get_identity dependency to return test identity."""
    app.dependency_overrides[get_identity] = lambda: test_identity
    yield
    app.dependency_overrides.clear()


# ============================================================================
# HTTP Client Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def async_client(override_get_identity) -> AsyncIterator[AsyncClient]:
    """
    Create an async HTTP client for testing FastAPI endpoints.

    This fixture:
    1. Creates AsyncClient with ASGITransport
    2. Overrides get_identity dependency with test identity
    3. Yields client for test
    4. Cleans up after test
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


# ============================================================================
# Vault Mocking Fixtures
# ============================================================================

@pytest.fixture
def mock_vault():
    """
    Mock Vault encrypt_text and decrypt_text functions.

    Returns predictable encrypted values for testing:
    - encrypt_text returns b"encrypted_" + original.encode()
    - decrypt_text removes b"encrypted_" prefix and decodes
    """
    async def mock_encrypt(key_path: str, plaintext: str, context=None) -> bytes:
        return b"vault:v1:encrypted_" + plaintext.encode("utf-8")

    async def mock_decrypt(key_path: str, ciphertext_bytes: bytes, context=None) -> str:
        # Remove "vault:v1:encrypted_" prefix
        prefix = b"vault:v1:encrypted_"
        if ciphertext_bytes.startswith(prefix):
            return ciphertext_bytes[len(prefix):].decode("utf-8")
        # Fallback for different format
        return ciphertext_bytes.decode("utf-8")

    with patch("app.crypto.vault.encrypt_text", side_effect=mock_encrypt) as mock_enc, \
         patch("app.crypto.vault.decrypt_text", side_effect=mock_decrypt) as mock_dec:
        yield {"encrypt": mock_enc, "decrypt": mock_dec}


# ============================================================================
# RAG Service Mocking Fixtures
# ============================================================================

@pytest.fixture
def mock_rag_service():
    """
    Mock RAG service for file processing tests.

    Returns an AsyncMock with common methods:
    - index_document: Returns number of chunks (5 by default)
    - retrieve: Returns list of mock chunks
    - delete_file_index: Returns None
    """
    mock_service = AsyncMock()

    # Configure default return values
    mock_service.index_document.return_value = 5  # 5 chunks indexed
    mock_service.retrieve.return_value = [
        {
            "text": "Sample chunk 1 content",
            "score": 0.95,
            "metadata": {"page": 1}
        },
        {
            "text": "Sample chunk 2 content",
            "score": 0.87,
            "metadata": {"page": 2}
        }
    ]
    mock_service.delete_file_index.return_value = None

    return mock_service


@pytest.fixture
def mock_get_rag_service(mock_rag_service):
    """Mock the get_rag_service function to return mock RAG service."""
    with patch("app.services.rag_service.get_rag_service", return_value=mock_rag_service):
        yield mock_rag_service


# ============================================================================
# LLM Client Mocking Fixtures
# ============================================================================

@pytest.fixture
def mock_llm_clients():
    """
    Mock LLM client responses for AI endpoint tests.

    Returns mock responses for OpenAI, Anthropic, and xAI providers.
    """
    mock_responses = {
        "openai": {
            "content": "OpenAI draft response",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "latency_ms": 500
        },
        "anthropic": {
            "content": "Anthropic draft response",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "latency_ms": 600
        },
        "xai": {
            "content": "xAI draft response",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "latency_ms": 450
        }
    }

    async def mock_fanout(messages):
        return mock_responses

    with patch("app.llm.clients.fanout_with_history", side_effect=mock_fanout):
        yield mock_responses


# ============================================================================
# File Processing Mocking Fixtures
# ============================================================================

@pytest.fixture
def mock_file_processor():
    """Mock FileProcessor for file upload tests."""
    mock_processor = MagicMock()

    async def mock_process_file(file_content: bytes, mime_type: str):
        return {
            "text": "Extracted file content",
            "use_direct_context": len(file_content) <= 50000
        }

    mock_processor.process_file = mock_process_file

    with patch("app.services.file_processor.FileProcessor", return_value=mock_processor):
        yield mock_processor


# ============================================================================
# Utility Functions
# ============================================================================

@pytest.fixture
def create_test_document(db_session, mock_vault):
    """
    Factory fixture to create test documents.

    Usage:
        doc_id = await create_test_document(
            title="Test Doc",
            content="Test content"
        )
    """
    async def _create_document(
        title: str = "Test Document",
        content: str = "Test content",
        created_by: str = TEST_USER_ID
    ) -> str:
        from app.crypto.vault import encrypt_text

        content_enc = await encrypt_text(TEST_VAULT_KEY, content)

        result = await db_session.execute(text("""
            INSERT INTO documents (title, content_enc, created_by)
            VALUES (:title, :content_enc, :created_by)
            RETURNING id
        """), {
            "title": title,
            "content_enc": content_enc,
            "created_by": created_by
        })

        doc_id = result.scalar_one()
        await db_session.commit()
        return str(doc_id)

    return _create_document


@pytest.fixture
def create_test_thread(db_session):
    """
    Factory fixture to create test chat threads.

    Usage:
        thread_id = await create_test_thread(
            document_id=doc_id,
            title="Test Thread"
        )
    """
    async def _create_thread(
        document_id: str = None,
        title: str = "Test Thread",
        created_by: str = TEST_USER_ID
    ) -> str:
        result = await db_session.execute(text("""
            INSERT INTO chat_threads (document_id, title, created_by)
            VALUES (:document_id, :title, :created_by)
            RETURNING id
        """), {
            "document_id": document_id,
            "title": title,
            "created_by": created_by
        })

        thread_id = result.scalar_one()
        await db_session.commit()
        return str(thread_id)

    return _create_thread


@pytest.fixture
def create_test_message(db_session, mock_vault):
    """
    Factory fixture to create test chat messages.

    Usage:
        message_id = await create_test_message(
            thread_id=thread_id,
            text="Test message"
        )
    """
    async def _create_message(
        thread_id: str,
        text: str = "Test message",
        role: str = "user"
    ) -> str:
        from app.crypto.vault import encrypt_text

        text_enc = await encrypt_text(TEST_VAULT_KEY, text)
        sanitized_enc = await encrypt_text(TEST_VAULT_KEY, text)  # Same for test

        result = await db_session.execute(text("""
            INSERT INTO chat_messages (thread_id, role, text_enc, sanitized_enc)
            VALUES (:thread_id, :role, :text_enc, :sanitized_enc)
            RETURNING id
        """), {
            "thread_id": thread_id,
            "role": role,
            "text_enc": text_enc,
            "sanitized_enc": sanitized_enc
        })

        message_id = result.scalar_one()
        await db_session.commit()
        return str(message_id)

    return _create_message
