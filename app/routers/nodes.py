import json
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.auth import get_current_user
from app.database import get_db
from app.models import oid, serialize_id
from app.services import nodes as node_service
from app.templating import templates
from app.urls import url as base_url

router = APIRouter()

UPLOAD_DIR = "app/static/uploads"


async def _authorized_node(db: AsyncIOMotorDatabase, node_id: str, username: str) -> dict:
    node = await node_service.get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    if not node_service.can_access(node, username):
        raise HTTPException(status_code=403, detail="Not authorized")
    return node


@router.get("/")
@router.get("/index.html")
async def index(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(request, "index.html", {"user": user})


@router.get("/api/tree")
async def tree(request: Request, db: AsyncIOMotorDatabase = Depends(get_db), user: dict = Depends(get_current_user)):
    await node_service.ensure_root(db, "admin")
    data = await node_service.build_tree(db, user["username"])
    return templates.TemplateResponse(request, "partials/tree.html", {"tree": data, "user": user})


@router.get("/api/nodes/{node_id}")
async def load_node(
    request: Request,
    node_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    node = await _authorized_node(db, node_id, user["username"])
    return templates.TemplateResponse(
        request, "partials/editor.html", {"node": serialize_id(node), "data": node.get("data") or {}}
    )


@router.post("/api/nodes")
async def create_node(
    request: Request,
    node_id: str = Form(...),
    name: str = Form(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    parent = await _authorized_node(db, node_id, user["username"])
    child = await node_service.add_node(db, parent, name, user["username"])
    data = await node_service.build_tree(db, user["username"])
    return templates.TemplateResponse(
        request,
        "partials/tree.html",
        {"tree": data, "user": user, "select_id": str(child["_id"])},
    )


@router.put("/api/nodes/{node_id}/rename")
async def rename_node(
    request: Request,
    node_id: str,
    name: str = Form(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    node = await _authorized_node(db, node_id, user["username"])
    await node_service.rename_node(db, node, name)
    data = await node_service.build_tree(db, user["username"])
    return templates.TemplateResponse(request, "partials/tree.html", {"tree": data, "user": user})


@router.delete("/api/nodes/{node_id}")
async def delete_node(
    request: Request,
    node_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    node = await _authorized_node(db, node_id, user["username"])
    try:
        await node_service.remove_node(db, node)
    except node_service.NodeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    data = await node_service.build_tree(db, user["username"])
    return templates.TemplateResponse(request, "partials/tree.html", {"tree": data, "user": user})


@router.post("/api/nodes/{node_id}/move")
async def move_node(
    request: Request,
    node_id: str,
    parent_id: str = Form(...),
    position: str = Form(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    node = await _authorized_node(db, node_id, user["username"])
    target = await _authorized_node(db, parent_id, user["username"])
    try:
        await node_service.move_node(db, node, target, position)
    except node_service.NodeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    data = await node_service.build_tree(db, user["username"])
    return templates.TemplateResponse(request, "partials/tree.html", {"tree": data, "user": user, "select_id": node_id})


@router.post("/api/nodes/{node_id}/copy")
async def copy_node(
    request: Request,
    node_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    node = await _authorized_node(db, node_id, user["username"])
    try:
        clone = await node_service.copy_node(db, node, user["username"])
    except node_service.NodeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    data = await node_service.build_tree(db, user["username"])
    return templates.TemplateResponse(
        request, "partials/tree.html", {"tree": data, "user": user, "select_id": str(clone["_id"])}
    )


@router.put("/api/nodes/{node_id}")
async def save_node(
    request: Request,
    node_id: str,
    data: str = Form(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    node = await _authorized_node(db, node_id, user["username"])
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid data")

    await node_service.save_node_data(db, node, parsed, user["username"])
    tree_data = await node_service.build_tree(db, user["username"])
    response = templates.TemplateResponse(
        request,
        "partials/save_result.html",
        {
            "msg": "Saved",
            "tree": tree_data,
            "user": user,
            "select_id": node_id,
            "node": serialize_id(node),
            "data": node.get("data") or {},
        },
    )
    return response


@router.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    original_name = os.path.basename(file.filename or "upload")
    ext = os.path.splitext(original_name)[1][:16]
    safe_name = f"{uuid.uuid4().hex}{ext}"

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    dest_path = os.path.join(UPLOAD_DIR, safe_name)

    with open(dest_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)

    return {"status": "ok", "url": base_url(f"/static/uploads/{safe_name}"), "name": original_name}


@router.get("/api/search")
async def search(
    request: Request,
    term: str = "",
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    results = []
    if term.strip():
        docs = await node_service.search_nodes(db, term, user["username"])
        results = [
            {"id": str(d["_id"]), "name": d.get("name", "???"), "content": (d.get("content") or "")[:300]}
            for d in docs
        ]
    return templates.TemplateResponse(request, "partials/search_results.html", {"term": term, "results": results})
