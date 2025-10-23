"""
Tests for bootstrap endpoint.

This module tests the /bootstrap/member-schema endpoint which creates
per-tenant database schemas and tables.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import text


class TestBootstrapMemberSchema:
    """Tests for member schema bootstrap endpoint."""

    @pytest.mark.asyncio
    async def test_bootstrap_creates_schema_successfully(
        self, async_client: AsyncClient, db_session, test_engine
    ):
        """Should create member schema with all tables when organization exists."""
        response = await async_client.post("/bootstrap/member-schema")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["schema"] == "test_mem_01"
        assert data["executed"] > 0  # Should execute multiple SQL statements

    @pytest.mark.asyncio
    async def test_bootstrap_is_idempotent(
        self, async_client: AsyncClient, db_session
    ):
        """Should succeed when called multiple times (idempotent operation)."""
        # First call
        response1 = await async_client.post("/bootstrap/member-schema")
        assert response1.status_code == 200

        # Second call should also succeed
        response2 = await async_client.post("/bootstrap/member-schema")
        assert response2.status_code == 200

        data = response2.json()
        assert data["ok"] is True

    @pytest.mark.asyncio
    async def test_bootstrap_creates_all_required_tables(
        self, async_client: AsyncClient, db_session
    ):
        """Should create all required tables in member schema."""
        await async_client.post("/bootstrap/member-schema")

        # Check that key tables exist
        required_tables = [
            "documents",
            "doc_versions",
            "chat_threads",
            "chat_messages",
            "ai_requests",
            "ai_responses",
            "ai_selections",
            "audit_logs",
            "uploaded_files",
        ]

        for table_name in required_tables:
            result = await db_session.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'test_mem_01'
                        AND table_name = :table_name
                    )
                """),
                {"table_name": table_name}
            )
            exists = result.scalar()
            assert exists, f"Table {table_name} should exist in test_mem_01 schema"

    @pytest.mark.asyncio
    async def test_bootstrap_creates_indexes(
        self, async_client: AsyncClient, db_session
    ):
        """Should create indexes for performance optimization."""
        await async_client.post("/bootstrap/member-schema")

        # Check that some key indexes exist
        result = await db_session.execute(
            text("""
                SELECT count(*)
                FROM pg_indexes
                WHERE schemaname = 'test_mem_01'
                AND indexname LIKE 'idx_%'
            """)
        )
        index_count = result.scalar()
        assert index_count > 0, "Should create performance indexes"

    @pytest.mark.asyncio
    async def test_bootstrap_without_organization_fails(
        self, async_client: AsyncClient, test_identity
    ):
        """Should return 404 when organization not found in control.members."""
        from app.main import app
        from app.security import get_identity, Identity

        # Override with non-existent org
        fake_identity = Identity(user_id="fake_user", org_id="non_existent_org")
        app.dependency_overrides[get_identity] = lambda: fake_identity

        try:
            response = await async_client.post("/bootstrap/member-schema")

            assert response.status_code == 404
            data = response.json()
            assert "not found" in data["detail"].lower()
        finally:
            # Restore original override
            app.dependency_overrides[get_identity] = lambda: test_identity

    @pytest.mark.asyncio
    async def test_bootstrap_with_sql_injection_attempt(
        self, async_client: AsyncClient, test_identity
    ):
        """Should safely handle malicious schema names (SQL injection attempt)."""
        from app.main import app
        from app.security import get_identity, Identity

        # Try to inject malicious org_id
        # This test verifies that the system uses parameterized queries
        malicious_identity = Identity(
            user_id="test_user",
            org_id="test'; DROP TABLE documents; --"
        )
        app.dependency_overrides[get_identity] = lambda: malicious_identity

        try:
            # Should fail because org doesn't exist, not because of SQL injection
            response = await async_client.post("/bootstrap/member-schema")

            # Should return 404 (org not found), not 500 (SQL error)
            assert response.status_code == 404
        finally:
            # Restore original override
            app.dependency_overrides[get_identity] = lambda: test_identity

    @pytest.mark.asyncio
    async def test_bootstrap_creates_foreign_key_constraints(
        self, async_client: AsyncClient, db_session
    ):
        """Should create foreign key constraints between tables."""
        await async_client.post("/bootstrap/member-schema")

        # Check for foreign key constraints
        result = await db_session.execute(
            text("""
                SELECT count(*)
                FROM information_schema.table_constraints
                WHERE constraint_schema = 'test_mem_01'
                AND constraint_type = 'FOREIGN KEY'
            """)
        )
        fk_count = result.scalar()
        assert fk_count > 0, "Should create foreign key constraints"

    @pytest.mark.asyncio
    async def test_bootstrap_response_structure(
        self, async_client: AsyncClient
    ):
        """Should return response with expected structure."""
        response = await async_client.post("/bootstrap/member-schema")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "ok" in data
        assert "schema" in data
        assert "executed" in data

        # Verify types
        assert isinstance(data["ok"], bool)
        assert isinstance(data["schema"], str)
        assert isinstance(data["executed"], int)

    @pytest.mark.asyncio
    async def test_bootstrap_concurrent_requests(
        self, async_client: AsyncClient
    ):
        """Should handle concurrent bootstrap requests safely."""
        import asyncio

        # Make 3 concurrent bootstrap requests
        tasks = [
            async_client.post("/bootstrap/member-schema")
            for _ in range(3)
        ]
        responses = await asyncio.gather(*tasks)

        # All should succeed (idempotent)
        assert all(r.status_code == 200 for r in responses)
        assert all(r.json()["ok"] is True for r in responses)

    @pytest.mark.asyncio
    async def test_bootstrap_table_column_types(
        self, async_client: AsyncClient, db_session
    ):
        """Should create tables with correct column types."""
        await async_client.post("/bootstrap/member-schema")

        # Check documents table columns
        result = await db_session.execute(
            text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'test_mem_01'
                AND table_name = 'documents'
                ORDER BY ordinal_position
            """)
        )

        columns = {row[0]: row[1] for row in result}

        # Verify key column types
        assert columns["id"] == "uuid"
        assert columns["title"] == "text"
        assert columns["content_enc"] == "bytea"
        assert columns["created_at"] in ["timestamp with time zone", "timestamp without time zone"]

    @pytest.mark.asyncio
    async def test_bootstrap_default_values(
        self, async_client: AsyncClient, db_session
    ):
        """Should set up default values for timestamp columns."""
        await async_client.post("/bootstrap/member-schema")

        # Insert a test document to verify defaults work
        result = await db_session.execute(
            text("""
                INSERT INTO documents (title, content_enc, created_by)
                VALUES ('Test', 'test_content'::bytea, 'test_user')
                RETURNING created_at, updated_at
            """)
        )

        row = result.first()
        assert row[0] is not None, "created_at should have default value"
        assert row[1] is not None, "updated_at should have default value"

    @pytest.mark.asyncio
    async def test_bootstrap_cascade_deletes_configured(
        self, async_client: AsyncClient, db_session
    ):
        """Should configure cascade deletes for related records."""
        await async_client.post("/bootstrap/member-schema")

        # Insert test data
        await db_session.execute(
            text("""
                INSERT INTO documents (id, title, content_enc, created_by)
                VALUES ('11111111-1111-1111-1111-111111111111', 'Test', 'content'::bytea, 'user')
            """)
        )
        await db_session.execute(
            text("""
                INSERT INTO doc_versions (document_id, version, content_enc)
                VALUES ('11111111-1111-1111-1111-111111111111', 1, 'content'::bytea)
            """)
        )
        await db_session.commit()

        # Delete document
        await db_session.execute(
            text("DELETE FROM documents WHERE id = '11111111-1111-1111-1111-111111111111'")
        )
        await db_session.commit()

        # Check that version was cascade deleted
        result = await db_session.execute(
            text("""
                SELECT count(*)
                FROM doc_versions
                WHERE document_id = '11111111-1111-1111-1111-111111111111'
            """)
        )
        count = result.scalar()
        assert count == 0, "doc_versions should be cascade deleted with document"
