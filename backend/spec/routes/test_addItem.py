import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.models import ItemCreate
from src.routes.items import add_item
from src.models import Classification

CLASSIFICATION = Classification(category="study", priority="high")


@pytest.mark.asyncio
async def test_it_stores_item_correctly():
    item_id = "something-not-a-uuid"
    name = "A sample item"
    expected_item = {
        "id": item_id,
        "name": name,
        "completed": False,
        "category": "study",
        "priority": "high",
        "registered": False,
        "due_date": None,
        "due_time": None,
    }

    with (
        patch("src.routes.items.uuid.uuid4", return_value=item_id),
        patch("src.ai.classify_item", new_callable=AsyncMock, return_value=CLASSIFICATION),
    ):
        with patch("src.persistence.store_item", new_callable=AsyncMock) as mock_store:
            result = await add_item(ItemCreate(name=name))

            assert mock_store.call_count == 1
            assert mock_store.call_args[0][0] == expected_item
            assert result == expected_item


@pytest.mark.asyncio
async def test_post_items_api_endpoint():
    item_id = "something-not-a-uuid"
    name = "A sample item"
    expected_item = {
        "id": item_id,
        "name": name,
        "completed": False,
        "category": "study",
        "priority": "high",
        "registered": False,
        "due_date": None,
        "due_time": None,
    }

    with (
        patch("src.routes.items.uuid.uuid4", return_value=item_id),
        patch("src.ai.classify_item", new_callable=AsyncMock, return_value=CLASSIFICATION),
    ):
        with patch("src.persistence.store_item", new_callable=AsyncMock) as mock_store:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post("/api/items", json={"name": name})

            assert response.status_code == 200
            assert response.json() == expected_item
            assert mock_store.call_count == 1


@pytest.mark.asyncio
async def test_it_stores_item_without_classification_when_ai_unavailable():
    item_id = "something-not-a-uuid"
    name = "A sample item"
    expected_item = {
        "id": item_id,
        "name": name,
        "completed": False,
        "category": None,
        "priority": None,
        "registered": False,
        "due_date": None,
        "due_time": None,
    }

    with (
        patch("src.routes.items.uuid.uuid4", return_value=item_id),
        patch("src.ai.classify_item", new_callable=AsyncMock, return_value=None),
    ):
        with patch("src.persistence.store_item", new_callable=AsyncMock) as mock_store:
            result = await add_item(ItemCreate(name=name))

            assert mock_store.call_args[0][0] == expected_item
            assert result == expected_item
