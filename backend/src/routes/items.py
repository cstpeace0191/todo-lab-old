import uuid
import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Response, status
from ..models import BulkDelete, BulkDeleteResult, Category, CategoryCount, Item, ItemCreate, ItemUpdate, valid_date
from .. import persistence as db
from .. import ai

router = APIRouter(tags=["items"])


@router.get("/api/items", response_model=List[Item])
@router.get("/items", response_model=List[Item], include_in_schema=False)
async def get_items(
    q: Optional[str] = None,
    category: Optional[Category] = None,
    registered: Optional[bool] = None,
    completed: Optional[bool] = None,
):
    """할 일 목록 조회.

    - q: 이름에 q 가 포함된 항목만 (대소문자 무시)
    - category: 해당 분류의 항목만
    - registered: true 면 등록된 항목, false 면 미등록(작업 중) 항목만
    - completed: true 면 완료된 항목, false 면 미완료 항목만 (생략 시 전체)
    """
    items = await db.get_items(q, category, registered)
    if completed is not None:
        items = [item for item in items if item["completed"] == completed]
    return items


@router.get("/api/categories", response_model=List[CategoryCount])
async def get_categories(registered: Optional[bool] = None):
    """분류별 항목 개수 (분류 선택 목록용)"""
    return await db.get_category_counts(registered)


@router.get("/api/schedule", response_model=List[Item])
async def get_schedule(
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD, 기본값은 서버 오늘"),
    start: Optional[str] = Query(default=None, description="기간 조회 시작일 YYYY-MM-DD (end 와 함께)"),
    end: Optional[str] = Query(default=None, description="기간 조회 종료일 YYYY-MM-DD (start 와 함께)"),
):
    """일정 조회 (등록 여부와 무관, 날짜·시간순).

    - start, end 를 주면: 기한이 start~end(양끝 포함) 사이인 항목 (주간/월간/연간/캘린더 검색)
    - 아니면: date(기본 오늘) 일정 + 기한이 지났지만 아직 완료하지 않은 항목 (오늘 일정)
    """
    if start is not None or end is not None:
        if start is None or end is None:
            raise HTTPException(status_code=422, detail="start and end must be given together")
        if date is not None:
            raise HTTPException(status_code=422, detail="use either date or start/end, not both")
        if valid_date(start) is None or valid_date(end) is None:
            raise HTTPException(status_code=422, detail="start and end must be valid YYYY-MM-DD dates")
        if start > end:
            raise HTTPException(status_code=422, detail="start must not be after end")
        return await db.get_schedule_range(start, end)

    day = date or datetime.date.today().isoformat()
    if valid_date(day) is None:
        raise HTTPException(status_code=422, detail="date must be a valid YYYY-MM-DD date")
    return await db.get_schedule(day)


@router.post("/api/items", response_model=Item, status_code=status.HTTP_200_OK)
@router.post("/items", response_model=Item, status_code=status.HTTP_200_OK, include_in_schema=False)
async def add_item(payload: ItemCreate):
    # Claude 로 카테고리/우선순위 자동 분류 (실패하면 None 으로 저장)
    classification = await ai.classify_item(payload.name, payload.today)

    # 사용자가 날짜를 직접 지정했으면 그것을 우선, 아니면 AI 가 추출한 값
    if payload.due_date:
        due_date, due_time = payload.due_date, payload.due_time
    else:
        due_date = classification.due_date if classification else None
        due_time = classification.due_time if classification else None

    new_item = {
        "id": str(uuid.uuid4()),
        "name": payload.name,
        "completed": False,
        "category": classification.category if classification else None,
        "priority": classification.priority if classification else None,
        "registered": False,
        "due_date": due_date,
        "due_time": due_time,
    }
    await db.store_item(new_item)
    return new_item


@router.put("/api/items/{item_id}", response_model=Item)
@router.put("/items/{item_id}", response_model=Item, include_in_schema=False)
async def update_item(item_id: str, payload: ItemUpdate):
    existing_item = await db.get_item(item_id)
    if not existing_item:
        raise HTTPException(status_code=404, detail="Item not found")

    # due_date/due_time: None 이면 유지, "" 이면 삭제, 값이면 변경. 날짜를 지우면 시간도 지운다.
    due_date = existing_item.get("due_date")
    due_time = existing_item.get("due_time")
    if payload.due_date is not None:
        due_date = payload.due_date or None
    if payload.due_time is not None:
        due_time = payload.due_time or None
    if due_date is None:
        due_time = None

    updated_data = {
        "name": payload.name if payload.name is not None else existing_item["name"],
        "completed": payload.completed if payload.completed is not None else existing_item["completed"],
        "category": payload.category if payload.category is not None else existing_item.get("category"),
        "priority": payload.priority if payload.priority is not None else existing_item.get("priority"),
        "registered": payload.registered if payload.registered is not None else existing_item.get("registered", False),
        "due_date": due_date,
        "due_time": due_time,
    }
    await db.update_item(item_id, updated_data)
    item = await db.get_item(item_id)
    return item


@router.post("/api/items/{item_id}/classify", response_model=Item)
async def classify_existing_item(item_id: str, today: Optional[str] = None):
    """기존 할 일을 Claude 로 다시 분류한다 (분류 전 항목, 이름 변경 후 등)."""
    existing_item = await db.get_item(item_id)
    if not existing_item:
        raise HTTPException(status_code=404, detail="Item not found")

    if not ai.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="AI classification is disabled (ANTHROPIC_API_KEY not set)",
        )

    classification = await ai.classify_item(existing_item["name"], valid_date(today))
    if classification is None:
        raise HTTPException(status_code=502, detail="AI classification failed")

    updated_data = {
        "name": existing_item["name"],
        "completed": existing_item["completed"],
        "category": classification.category,
        "priority": classification.priority,
        "registered": existing_item.get("registered", False),
        # AI 가 새 일정을 찾았을 때만 갱신하고, 못 찾으면 기존(수동 지정 포함) 값을 유지
        "due_date": classification.due_date or existing_item.get("due_date"),
        "due_time": (
            classification.due_time
            if classification.due_date
            else existing_item.get("due_time")
        ),
    }
    await db.update_item(item_id, updated_data)
    return await db.get_item(item_id)


@router.get("/api/ai/status")
async def ai_status():
    """클라이언트가 AI 분류 버튼을 보여줄지 결정할 때 사용"""
    return {"enabled": ai.is_enabled()}


@router.delete("/api/items/{item_id}", status_code=status.HTTP_200_OK)
@router.delete("/items/{item_id}", status_code=status.HTTP_200_OK, include_in_schema=False)
async def delete_item(item_id: str):
    await db.remove_item(item_id)
    return Response(status_code=status.HTTP_200_OK)


@router.post("/api/items/bulk-delete", response_model=BulkDeleteResult)
async def bulk_delete_items(payload: BulkDelete):
    """선택한 여러 항목을 한 번에 삭제한다. 존재하지 않는 id 는 무시하고 삭제된 개수를 돌려준다."""
    unique_ids = list(dict.fromkeys(payload.ids))  # 중복 제거 (순서 유지)
    deleted = await db.remove_items(unique_ids)
    return {"deleted": deleted}
