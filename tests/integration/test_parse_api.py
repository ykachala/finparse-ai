"""
Integration tests for the parse and documents API endpoints.

Uses pytest-asyncio + httpx AsyncClient. Mocks external dependencies
(S3, Celery, Claude) to keep tests self-contained.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="module")
def app():
    # Patch settings before importing the app to avoid validation errors
    with (
        patch("src.config.Settings.__init__", return_value=None),
        patch("src.config.get_settings") as mock_settings,
        patch("src.storage.database.init_db"),
        patch("src.storage.database.get_db"),
        patch("src.workers.celery_app.get_settings") as _,
    ):
        settings = MagicMock()
        settings.database_url = "postgresql+asyncpg://test:test@localhost/test"
        settings.max_file_size_mb = 20
        settings.max_batch_size = 50
        settings.sync_parse_timeout_seconds = 30
        mock_settings.return_value = settings

        from src.main import create_app
        return create_app()


@pytest.mark.asyncio
async def test_health_endpoint(app) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_parse_requires_auth(app) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("src.storage.database.get_db") as mock_db:
            mock_db.return_value.__aiter__ = AsyncMock(return_value=iter([MagicMock()]))
            from io import BytesIO
            response = await client.post(
                "/api/v1/parse",
                files={"file": ("test.pdf", BytesIO(b"%PDF-1.4"), "application/pdf")},
            )
    # 403 or 401 — no auth header provided
    assert response.status_code in (401, 403, 422)


@pytest.mark.asyncio
async def test_documents_requires_auth(app) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/documents")
    assert response.status_code in (401, 403, 422)
