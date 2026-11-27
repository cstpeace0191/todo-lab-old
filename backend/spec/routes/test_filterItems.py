import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from src.main import app

ITEMS = [
    {"id": "1", "name": "장보기", "completed": True},
    {"id": "2", "name": "과제 제출", "completed": False},
    {"id": "3", "name": "운동", "completed": False},
]


async def _get(url: str):
    with patch("src.persistence.get_items", new_callable=AsyncMock, return_value=ITEMS):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            return await ac.get(url)


@pytest.mark.asyncio
async def test_without_filter_returns_all():
    response = await _get("/api/items")
    assert response.status_code == 200
    assert len(response.json()) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("value,expected_ids", [("true", ["1"]), ("false", ["2", "3"])])
async def test_filter_by_completed(value, expected_ids):
    response = await _get(f"/api/items?completed={value}")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == expected_ids


@pytest.mark.asyncio
async def test_invalid_filter_value_returns_422():
    response = await _get("/api/items?completed=maybe")
    assert response.status_code == 422
