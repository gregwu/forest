from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.auth import get_current_user
from app.database import get_db
from app.services import nodes as node_service
from app.services import publish as publish_service

router = APIRouter()


async def _root_ancestor(db: AsyncIOMotorDatabase, node: dict) -> dict:
    """Walk up to the nearest ancestor named 'All' or ending in .html, matching original publish() JS logic."""
    current = node
    while current.get("name") not in ("All",) and not current["name"].endswith(".html"):
        parent_id = current.get("parent")
        if parent_id is None:
            break
        current = await db.nodes.find_one({"_id": parent_id})
    return current


@router.post("/api/nodes/{node_id}/publish")
async def publish_node(node_id: str, db: AsyncIOMotorDatabase = Depends(get_db), user: dict = Depends(get_current_user)):
    node = await node_service.get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    if not node_service.can_access(node, user["username"]):
        raise HTTPException(status_code=403, detail="Not authorized")

    target = await _root_ancestor(db, node)
    try:
        path = await publish_service.publish_node(db, target)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "path": path}


@router.get("/api/nodes/{node_id}/preview", response_class=HTMLResponse)
async def preview_node(node_id: str, db: AsyncIOMotorDatabase = Depends(get_db), user: dict = Depends(get_current_user)):
    node = await node_service.get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    if not node_service.can_access(node, user["username"]):
        raise HTTPException(status_code=403, detail="Not authorized")

    html = await publish_service.preview_node(db, node)
    return HTMLResponse(html)
