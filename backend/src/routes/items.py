import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Response, status
from ..models import Item, ItemCreate, ItemUpdate
from .. import persistence as db

router = APIRouter(tags=["items"])


@router.get("/api/items", response_model=List[Item])
@router.get("/items", response_model=List[Item], include_in_schema=False)
async def get_items(completed: Optional[bool] = None):
    """완료 여부로 필터링: /api/items?completed=true|false (생략 시 전체)"""
    items = await db.get_items()
    if completed is not None:
        items = [item for item in items if item["completed"] == completed]
    return items


@router.post("/api/items", response_model=Item, status_code=status.HTTP_200_OK)
@router.post("/items", response_model=Item, status_code=status.HTTP_200_OK, include_in_schema=False)
async def add_item(payload: ItemCreate):
    new_item = {
        "id": str(uuid.uuid4()),
        "name": payload.name,
        "completed": False,
    }
    await db.store_item(new_item)
    return new_item


@router.put("/api/items/{item_id}", response_model=Item)
@router.put("/items/{item_id}", response_model=Item, include_in_schema=False)
async def update_item(item_id: str, payload: ItemUpdate):
    existing_item = await db.get_item(item_id)
    if not existing_item:
        raise HTTPException(status_code=404, detail="Item not found")

    updated_data = {
        "name": payload.name if payload.name is not None else existing_item["name"],
        "completed": payload.completed if payload.completed is not None else existing_item["completed"],
    }
    await db.update_item(item_id, updated_data)
    item = await db.get_item(item_id)
    return item


@router.delete("/api/items/{item_id}", status_code=status.HTTP_200_OK)
@router.delete("/items/{item_id}", status_code=status.HTTP_200_OK, include_in_schema=False)
async def delete_item(item_id: str):
    await db.remove_item(item_id)
    return Response(status_code=status.HTTP_200_OK)
