from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.models import Classification

ITEM = {
    "id": "1234",
    "name": "보고서 작성",
    "completed": False,
    "category": None,
    "priority": None,
    "registered": False,
    "due_date": None,
    "due_time": None,
}
CLASSIFIED = {**ITEM, "category": "work", "priority": "high"}


async def _post(path: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.post(path)


@pytest.mark.asyncio
async def test_classify_endpoint_updates_item():
    with patch("src.persistence.get_item", new_callable=AsyncMock, side_effect=[ITEM, CLASSIFIED]), \
            patch("src.persistence.update_item", new_callable=AsyncMock) as mock_update, \
            patch("src.ai.is_enabled", return_value=True), \
            patch("src.ai.classify_item", new_callable=AsyncMock,
                  return_value=Classification(category="work", priority="high")):
        response = await _post("/api/items/1234/classify")

    assert response.status_code == 200
    assert response.json() == CLASSIFIED
    assert mock_update.call_args[0] == (
        "1234",
        {
            "name": "보고서 작성",
            "completed": False,
            "category": "work",
            "priority": "high",
            "registered": False,
            "due_date": None,
            "due_time": None,
        },
    )


@pytest.mark.asyncio
async def test_classify_endpoint_returns_404_for_missing_item():
    with patch("src.persistence.get_item", new_callable=AsyncMock, return_value=None):
        response = await _post("/api/items/nope/classify")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_classify_endpoint_returns_503_when_disabled():
    with patch("src.persistence.get_item", new_callable=AsyncMock, return_value=ITEM), \
            patch("src.ai.is_enabled", return_value=False):
        response = await _post("/api/items/1234/classify")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_classify_endpoint_returns_502_when_ai_fails():
    with patch("src.persistence.get_item", new_callable=AsyncMock, return_value=ITEM), \
            patch("src.persistence.update_item", new_callable=AsyncMock) as mock_update, \
            patch("src.ai.is_enabled", return_value=True), \
            patch("src.ai.classify_item", new_callable=AsyncMock, return_value=None):
        response = await _post("/api/items/1234/classify")

    assert response.status_code == 502
    assert mock_update.call_count == 0


@pytest.mark.asyncio
async def test_ai_status_endpoint():
    with patch("src.ai.is_enabled", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/ai/status")

    assert response.json() == {"enabled": True}
