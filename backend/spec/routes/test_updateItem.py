import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.models import ItemUpdate
from src.routes.items import update_item

ITEM = {
    "id": "1234",
    "name": "New title",
    "completed": False,
    "category": None,
    "priority": None,
    "registered": False,
    "due_date": None,
    "due_time": None,
}
# 라우트는 payload 에 없는 필드를 기존 항목 값으로 채워 전체 필드를 저장한다
EXPECTED_UPDATE = {k: v for k, v in ITEM.items() if k != "id"}


@pytest.mark.asyncio
async def test_it_updates_items_correctly():
    item_id = "1234"
    update_payload = {"name": "New title", "completed": False}

    with patch("src.persistence.get_item", new_callable=AsyncMock, return_value=ITEM):
        with patch("src.persistence.update_item", new_callable=AsyncMock) as mock_update:
            result = await update_item(item_id, ItemUpdate(**update_payload))

            assert mock_update.call_count == 1
            assert mock_update.call_args[0][0] == item_id
            assert mock_update.call_args[0][1] == EXPECTED_UPDATE
            assert result == ITEM


@pytest.mark.asyncio
async def test_update_items_api_endpoint():
    item_id = "1234"
    update_payload = {"name": "New title", "completed": False}

    with patch("src.persistence.get_item", new_callable=AsyncMock, return_value=ITEM):
        with patch("src.persistence.update_item", new_callable=AsyncMock) as mock_update:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.put(f"/api/items/{item_id}", json=update_payload)

            assert response.status_code == 200
            assert response.json() == ITEM
            assert mock_update.call_count == 1
