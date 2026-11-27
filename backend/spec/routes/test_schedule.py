from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.models import Classification
from src.routes.items import add_item
from src.models import ItemCreate

ITEM = {
    "id": "1",
    "name": "보고서",
    "completed": False,
    "category": "work",
    "priority": "high",
    "registered": False,
    "due_date": "2026-11-25",
    "due_time": "09:00",
}


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_schedule_endpoint_uses_given_date():
    with patch("src.persistence.get_schedule", new_callable=AsyncMock, return_value=[ITEM]) as mock_get:
        async with await _client() as ac:
            response = await ac.get("/api/schedule", params={"date": "2026-11-25"})

    assert response.status_code == 200
    assert response.json() == [ITEM]
    mock_get.assert_called_once_with("2026-11-25")


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["2026-13-01", "tomorrow", "2026-1-1"])
async def test_schedule_rejects_invalid_date(bad):
    async with await _client() as ac:
        response = await ac.get("/api/schedule", params={"date": bad})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_add_item_uses_ai_extracted_due_date_and_passes_today():
    classification = Classification(
        category="work", priority="high", due_date="2026-11-26", due_time="09:00"
    )
    with patch("src.ai.classify_item", new_callable=AsyncMock, return_value=classification) as mock_ai, \
            patch("src.persistence.store_item", new_callable=AsyncMock) as mock_store:
        result = await add_item(ItemCreate(name="내일 오전 9시 보고서", today="2026-11-25"))

    assert mock_ai.call_args[0] == ("내일 오전 9시 보고서", "2026-11-25")
    assert result["due_date"] == "2026-11-26"
    assert result["due_time"] == "09:00"
    assert mock_store.call_args[0][0]["due_date"] == "2026-11-26"


@pytest.mark.asyncio
async def test_manual_due_date_overrides_ai():
    classification = Classification(
        category="work", priority="high", due_date="2026-11-26", due_time="09:00"
    )
    with patch("src.ai.classify_item", new_callable=AsyncMock, return_value=classification), \
            patch("src.persistence.store_item", new_callable=AsyncMock):
        result = await add_item(
            ItemCreate(name="x", due_date="2026-12-01", due_time="14:30", today="2026-11-25")
        )

    assert (result["due_date"], result["due_time"]) == ("2026-12-01", "14:30")


@pytest.mark.asyncio
async def test_manual_date_without_time_does_not_borrow_ai_time():
    classification = Classification(
        category="work", priority="high", due_date="2026-11-26", due_time="09:00"
    )
    with patch("src.ai.classify_item", new_callable=AsyncMock, return_value=classification), \
            patch("src.persistence.store_item", new_callable=AsyncMock):
        result = await add_item(ItemCreate(name="x", due_date="2026-12-01"))

    assert (result["due_date"], result["due_time"]) == ("2026-12-01", None)


@pytest.mark.asyncio
async def test_add_item_rejects_invalid_due_values():
    async with await _client() as ac:
        bad_date = await ac.post("/api/items", json={"name": "x", "due_date": "2026-02-31"})
        bad_time = await ac.post("/api/items", json={"name": "x", "due_time": "25:00"})
    assert bad_date.status_code == 422
    assert bad_time.status_code == 422


@pytest.mark.asyncio
async def test_update_sets_and_clears_due_date():
    existing = {**ITEM}
    with patch("src.persistence.get_item", new_callable=AsyncMock, side_effect=[existing, existing]), \
            patch("src.persistence.update_item", new_callable=AsyncMock) as mock_update:
        async with await _client() as ac:
            await ac.put("/api/items/1", json={"due_date": "2026-12-24", "due_time": "10:15"})
    saved = mock_update.call_args[0][1]
    assert (saved["due_date"], saved["due_time"]) == ("2026-12-24", "10:15")

    with patch("src.persistence.get_item", new_callable=AsyncMock, side_effect=[existing, existing]), \
            patch("src.persistence.update_item", new_callable=AsyncMock) as mock_update:
        async with await _client() as ac:
            await ac.put("/api/items/1", json={"due_date": ""})
    saved = mock_update.call_args[0][1]
    # 날짜를 지우면 시간도 함께 지워진다
    assert (saved["due_date"], saved["due_time"]) == (None, None)


@pytest.mark.asyncio
async def test_update_without_due_fields_keeps_them():
    with patch("src.persistence.get_item", new_callable=AsyncMock, side_effect=[ITEM, ITEM]), \
            patch("src.persistence.update_item", new_callable=AsyncMock) as mock_update:
        async with await _client() as ac:
            await ac.put("/api/items/1", json={"completed": True})
    saved = mock_update.call_args[0][1]
    assert (saved["due_date"], saved["due_time"]) == ("2026-11-25", "09:00")


@pytest.mark.asyncio
async def test_classify_keeps_existing_due_when_ai_finds_none():
    with patch("src.persistence.get_item", new_callable=AsyncMock, side_effect=[ITEM, ITEM]), \
            patch("src.persistence.update_item", new_callable=AsyncMock) as mock_update, \
            patch("src.ai.is_enabled", return_value=True), \
            patch("src.ai.classify_item", new_callable=AsyncMock,
                  return_value=Classification(category="work", priority="low")):
        async with await _client() as ac:
            response = await ac.post("/api/items/1/classify", params={"today": "2026-11-25"})

    assert response.status_code == 200
    saved = mock_update.call_args[0][1]
    assert (saved["due_date"], saved["due_time"]) == ("2026-11-25", "09:00")


@pytest.mark.asyncio
async def test_edit_updates_name_and_schedule_together():
    with patch("src.persistence.get_item", new_callable=AsyncMock, side_effect=[ITEM, ITEM]), \
            patch("src.persistence.update_item", new_callable=AsyncMock) as mock_update:
        async with await _client() as ac:
            response = await ac.put(
                "/api/items/1",
                json={"name": "수정된 내용", "due_date": "2026-12-01", "due_time": "16:45"},
            )

    assert response.status_code == 200
    saved = mock_update.call_args[0][1]
    assert saved["name"] == "수정된 내용"
    assert (saved["due_date"], saved["due_time"]) == ("2026-12-01", "16:45")
    # 수정하지 않은 값은 유지된다
    assert saved["category"] == ITEM["category"]
    assert saved["completed"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_name", ["", "   ", "x" * 256])
async def test_edit_rejects_empty_or_too_long_name(bad_name):
    with patch("src.persistence.update_item", new_callable=AsyncMock) as mock_update:
        async with await _client() as ac:
            response = await ac.put("/api/items/1", json={"name": bad_name})

    assert response.status_code == 422
    assert mock_update.call_count == 0


@pytest.mark.asyncio
async def test_edit_trims_name_whitespace():
    with (
        patch("src.persistence.get_item", new_callable=AsyncMock, side_effect=[ITEM, ITEM]),
        patch("src.persistence.update_item", new_callable=AsyncMock) as mock_update,
    ):
        async with await _client() as ac:
            await ac.put("/api/items/1", json={"name": "  앞뒤 공백  "})

    assert mock_update.call_args[0][1]["name"] == "앞뒤 공백"


@pytest.mark.asyncio
async def test_schedule_range_endpoint_uses_start_and_end():
    with patch("src.persistence.get_schedule_range", new_callable=AsyncMock, return_value=[ITEM]) as mock_range, \
            patch("src.persistence.get_schedule", new_callable=AsyncMock) as mock_day:
        async with await _client() as ac:
            response = await ac.get("/api/schedule", params={"start": "2026-11-23", "end": "2026-11-29"})

    assert response.status_code == 200
    assert response.json() == [ITEM]
    mock_range.assert_called_once_with("2026-11-23", "2026-11-29")
    assert mock_day.call_count == 0  # 기간 조회에는 '기한 지난 항목' 로직을 쓰지 않는다


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"start": "2026-11-23"},                                  # end 없음
        {"end": "2026-11-29"},                                    # start 없음
        {"start": "2026-11-30", "end": "2026-11-23"},             # 시작이 종료보다 늦음
        {"start": "2026-13-01", "end": "2026-13-02"},             # 존재하지 않는 날짜
        {"start": "nope", "end": "2026-11-29"},                   # 형식 오류
        {"date": "2026-11-25", "start": "2026-11-23", "end": "2026-11-29"},  # date 와 동시 사용
    ],
)
async def test_schedule_range_rejects_invalid_params(params):
    with patch("src.persistence.get_schedule_range", new_callable=AsyncMock) as mock_range:
        async with await _client() as ac:
            response = await ac.get("/api/schedule", params=params)

    assert response.status_code == 422
    assert mock_range.call_count == 0
