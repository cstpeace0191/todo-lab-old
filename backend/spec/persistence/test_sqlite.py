import os
import pytest
import pytest_asyncio
from src.persistence import sqlite as db

LOCATION = os.getenv("SQLITE_DB_LOCATION", "/etc/todos/todo.db")

ITEM = {
    "id": "7aef3d7c-d301-4846-8358-2a91ec9d6be3",
    "name": "Test",
    "completed": False,
    "category": "study",
    "priority": "high",
    "registered": False,
    "due_date": None,
    "due_time": None,
}


@pytest_asyncio.fixture(autouse=True)
async def cleanup():
    # Teardown any existing connections first
    await db.teardown()
    if os.path.exists(LOCATION):
        try:
            os.unlink(LOCATION)
        except Exception:
            pass
    yield
    await db.teardown()
    if os.path.exists(LOCATION):
        try:
            os.unlink(LOCATION)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_it_initializes_correctly():
    await db.init()


@pytest.mark.asyncio
async def test_it_can_store_and_retrieve_items():
    await db.init()
    await db.store_item(ITEM)

    items = await db.get_items()
    assert len(items) == 1
    assert items[0] == ITEM


@pytest.mark.asyncio
async def test_it_can_update_an_existing_item():
    await db.init()

    initial_items = await db.get_items()
    assert len(initial_items) == 0

    await db.store_item(ITEM)

    updated = dict(ITEM)
    updated["completed"] = not ITEM["completed"]
    await db.update_item(ITEM["id"], updated)

    items = await db.get_items()
    assert len(items) == 1
    assert items[0]["completed"] == (not ITEM["completed"])


@pytest.mark.asyncio
async def test_it_can_remove_an_existing_item():
    await db.init()
    await db.store_item(ITEM)

    await db.remove_item(ITEM["id"])

    items = await db.get_items()
    assert len(items) == 0


@pytest.mark.asyncio
async def test_it_can_get_a_single_item():
    await db.init()
    await db.store_item(ITEM)

    item = await db.get_item(ITEM["id"])
    assert item == ITEM


@pytest.mark.asyncio
async def test_it_migrates_an_old_schema_without_ai_columns():
    import aiosqlite

    # 예전 버전 스키마(id, name, completed)로 DB 파일을 먼저 만든다
    dirname = os.path.dirname(os.path.abspath(LOCATION))
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    async with aiosqlite.connect(LOCATION) as old:
        await old.execute(
            "CREATE TABLE todo_items (id VARCHAR(36), name VARCHAR(255), completed BOOLEAN)"
        )
        await old.execute("INSERT INTO todo_items VALUES ('old-1', 'Old item', 0)")
        await old.commit()

    await db.init()

    item = await db.get_item("old-1")
    assert item == {
        "id": "old-1",
        "name": "Old item",
        "completed": False,
        "category": None,
        "priority": None,
        "registered": False,
        "due_date": None,
        "due_time": None,
    }
    await db.store_item(ITEM)
    assert await db.get_item(ITEM["id"]) == ITEM


@pytest.mark.asyncio
async def test_it_can_search_items_by_name():
    await db.init()
    await db.store_item({**ITEM, "id": "1", "name": "Buy Milk"})
    await db.store_item({**ITEM, "id": "2", "name": "Write report"})
    await db.store_item({**ITEM, "id": "3", "name": "우유 사기"})

    assert [i["id"] for i in await db.get_items("milk")] == ["1"]
    assert [i["id"] for i in await db.get_items("우유")] == ["3"]
    assert await db.get_items("nothing") == []
    # 빈 검색어는 전체 목록
    assert len(await db.get_items("  ")) == 3


@pytest.mark.asyncio
async def test_search_treats_wildcards_literally():
    await db.init()
    await db.store_item({**ITEM, "id": "1", "name": "100% done"})
    await db.store_item({**ITEM, "id": "2", "name": "something else"})

    assert [i["id"] for i in await db.get_items("%")] == ["1"]
    assert await db.get_items("_") == []


@pytest.mark.asyncio
async def test_it_filters_by_registered_and_category():
    await db.init()
    await db.store_item({**ITEM, "id": "1", "name": "A", "category": "work", "registered": True})
    await db.store_item({**ITEM, "id": "2", "name": "B", "category": "study", "registered": True})
    await db.store_item({**ITEM, "id": "3", "name": "C", "category": "work", "registered": False})

    assert {i["id"] for i in await db.get_items(registered=True)} == {"1", "2"}
    assert {i["id"] for i in await db.get_items(registered=False)} == {"3"}
    assert {i["id"] for i in await db.get_items(category="work")} == {"1", "3"}
    # 분류 선택 + 키워드 + 등록 여부 조합
    assert [i["id"] for i in await db.get_items("a", "work", True)] == ["1"]
    assert await db.get_items("a", "study", True) == []


@pytest.mark.asyncio
async def test_it_counts_items_per_category():
    await db.init()
    await db.store_item({**ITEM, "id": "1", "category": "work", "registered": True})
    await db.store_item({**ITEM, "id": "2", "category": "work", "registered": True})
    await db.store_item({**ITEM, "id": "3", "category": "study", "registered": True})
    await db.store_item({**ITEM, "id": "4", "category": "study", "registered": False})
    await db.store_item({**ITEM, "id": "5", "category": None, "registered": True})

    assert await db.get_category_counts(registered=True) == [
        {"category": "study", "count": 1},
        {"category": "work", "count": 2},
    ]
    assert await db.get_category_counts() == [
        {"category": "study", "count": 2},
        {"category": "work", "count": 2},
    ]


@pytest.mark.asyncio
async def test_register_flag_is_persisted_on_update():
    await db.init()
    await db.store_item(ITEM)
    await db.update_item(ITEM["id"], {**ITEM, "registered": True})
    assert (await db.get_item(ITEM["id"]))["registered"] is True


@pytest.mark.asyncio
async def test_it_returns_todays_schedule_with_overdue_open_items():
    await db.init()
    day = "2026-11-25"
    await db.store_item({**ITEM, "id": "late-open", "name": "late", "due_date": "2026-11-20"})
    await db.store_item({**ITEM, "id": "late-done", "name": "done", "due_date": "2026-11-20", "completed": True})
    await db.store_item({**ITEM, "id": "t-pm", "name": "pm", "due_date": day, "due_time": "18:00"})
    await db.store_item({**ITEM, "id": "t-am", "name": "am", "due_date": day, "due_time": "09:00"})
    await db.store_item({**ITEM, "id": "t-any", "name": "anytime", "due_date": day})
    await db.store_item({**ITEM, "id": "t-done", "name": "today done", "due_date": day, "completed": True})
    await db.store_item({**ITEM, "id": "future", "name": "future", "due_date": "2026-11-26"})
    await db.store_item({**ITEM, "id": "nodate", "name": "nodate"})

    schedule = await db.get_schedule(day)

    # 지난 미완료 → 오늘(시간순, 시간 없는 항목은 마지막). 완료된 지난 항목/미래/날짜 없음은 제외.
    assert [i["id"] for i in schedule] == ["late-open", "t-am", "t-pm", "t-any", "t-done"]


@pytest.mark.asyncio
async def test_schedule_includes_registered_and_unregistered_items():
    await db.init()
    day = "2026-11-25"
    await db.store_item({**ITEM, "id": "1", "due_date": day, "registered": True})
    await db.store_item({**ITEM, "id": "2", "due_date": day, "registered": False})
    assert {i["id"] for i in await db.get_schedule(day)} == {"1", "2"}


@pytest.mark.asyncio
async def test_due_fields_are_persisted_and_migrated():
    await db.init()
    await db.store_item({**ITEM, "due_date": "2026-11-25", "due_time": "09:30"})
    item = await db.get_item(ITEM["id"])
    assert (item["due_date"], item["due_time"]) == ("2026-11-25", "09:30")

    await db.update_item(ITEM["id"], {**ITEM, "due_date": None, "due_time": None})
    item = await db.get_item(ITEM["id"])
    assert (item["due_date"], item["due_time"]) == (None, None)


@pytest.mark.asyncio
async def test_it_removes_many_items_at_once():
    await db.init()
    for n in range(5):
        await db.store_item({**ITEM, "id": f"id-{n}", "name": f"item {n}"})

    deleted = await db.remove_items(["id-0", "id-2", "id-4", "does-not-exist"])

    assert deleted == 3  # 존재하지 않는 id 는 세지 않는다
    assert {i["id"] for i in await db.get_items()} == {"id-1", "id-3"}


@pytest.mark.asyncio
async def test_bulk_remove_splits_large_id_lists_into_chunks(monkeypatch):
    # 실제 청크 크기(500)는 항목 수천 개가 필요하므로, 청크를 작게 줄여 같은 분할 로직을 검증한다
    monkeypatch.setattr(db, "_DELETE_CHUNK", 3)
    await db.init()
    ids = [f"id-{n}" for n in range(10)]
    for item_id in ids:
        await db.store_item({**ITEM, "id": item_id})
    await db.store_item({**ITEM, "id": "keep"})

    assert await db.remove_items(ids) == 10  # 3 + 3 + 3 + 1
    assert [i["id"] for i in await db.get_items()] == ["keep"]


@pytest.mark.asyncio
async def test_it_returns_items_within_a_date_range_inclusive():
    await db.init()
    cases = {
        "before": "2026-11-22",
        "start": "2026-11-23",
        "mid-pm": ("2026-11-25", "18:00"),
        "mid-am": ("2026-11-25", "09:00"),
        "end": "2026-11-29",
        "after": "2026-11-30",
    }
    for key, value in cases.items():
        due_date, due_time = value if isinstance(value, tuple) else (value, None)
        await db.store_item({**ITEM, "id": key, "name": key, "due_date": due_date, "due_time": due_time})
    await db.store_item({**ITEM, "id": "nodate", "name": "nodate"})
    # 완료한 항목도, 등록 여부와 상관없이 범위에 들어오면 포함된다
    await db.store_item(
        {**ITEM, "id": "done", "name": "done", "due_date": "2026-11-24", "completed": True, "registered": True}
    )

    result = await db.get_schedule_range("2026-11-23", "2026-11-29")

    assert [i["id"] for i in result] == ["start", "done", "mid-am", "mid-pm", "end"]


@pytest.mark.asyncio
async def test_range_with_same_start_and_end_returns_that_day_only():
    await db.init()
    await db.store_item({**ITEM, "id": "a", "due_date": "2026-11-25"})
    await db.store_item({**ITEM, "id": "b", "due_date": "2026-11-26"})
    assert [i["id"] for i in await db.get_schedule_range("2026-11-25", "2026-11-25")] == ["a"]
