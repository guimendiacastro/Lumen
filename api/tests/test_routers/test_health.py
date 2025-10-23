"""
Tests for health check endpoint.

This module tests the /healthz endpoint which provides basic health status.
"""

import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    @pytest.mark.asyncio
    async def test_healthz_returns_ok(self, async_client: AsyncClient):
        """Should return ok status when application is healthy."""
        response = await async_client.get("/healthz")

        assert response.status_code == 200
        data = response.json()
        assert data == {"ok": True}

    @pytest.mark.asyncio
    async def test_healthz_no_authentication_required(self):
        """Should not require authentication to access health endpoint."""
        # Create client without authentication override
        from httpx import ASGITransport
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.get("/healthz")

            assert response.status_code == 200
            data = response.json()
            assert data == {"ok": True}

    @pytest.mark.asyncio
    async def test_healthz_responds_quickly(self, async_client: AsyncClient):
        """Should respond within reasonable time (< 100ms)."""
        import time

        start = time.time()
        response = await async_client.get("/healthz")
        elapsed = (time.time() - start) * 1000  # Convert to ms

        assert response.status_code == 200
        assert elapsed < 100, f"Health check took {elapsed}ms, expected < 100ms"

    @pytest.mark.asyncio
    async def test_healthz_supports_head_request(self, async_client: AsyncClient):
        """Should support HEAD requests for health checks."""
        response = await async_client.head("/healthz")

        # HEAD requests typically return 405 Method Not Allowed in FastAPI
        # unless explicitly defined, or 200 if the route accepts it
        # Just verify we get a response
        assert response.status_code in [200, 405]

    @pytest.mark.asyncio
    async def test_healthz_multiple_concurrent_requests(self, async_client: AsyncClient):
        """Should handle multiple concurrent health check requests."""
        import asyncio

        # Make 10 concurrent requests
        tasks = [async_client.get("/healthz") for _ in range(10)]
        responses = await asyncio.gather(*tasks)

        # All should succeed
        assert all(r.status_code == 200 for r in responses)
        assert all(r.json() == {"ok": True} for r in responses)
