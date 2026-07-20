import json

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.auth import get_admin_user, login_user
from app.database import get_db
from app.models import oid
from app.services import nodes as node_service
from app.templating import templates
from app.urls import url as base_url

router = APIRouter()


@router.get("/users")
async def users_page(
    request: Request,
    msg: str = "",
    user: dict = Depends(get_admin_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    cursor = db.users.find({}, {"username": 1, "domain": 1, "is_admin": 1}).sort("domain", 1)
    users = []
    async for u in cursor:
        users.append(
            {
                "id": str(u["_id"]),
                "username": u["username"],
                "domain": u["domain"],
                "is_admin": bool(u.get("is_admin", False)),
            }
        )
    return templates.TemplateResponse(request, "users.html", {"users": users, "current_user": user, "msg": msg})


@router.post("/users/{user_id}/role")
async def change_role(
    user_id: str, is_admin: bool, admin: dict = Depends(get_admin_user), db: AsyncIOMotorDatabase = Depends(get_db)
):
    await db.users.update_one({"_id": oid(user_id)}, {"$set": {"is_admin": is_admin}})
    return {"status": "ok"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str, admin: dict = Depends(get_admin_user), db: AsyncIOMotorDatabase = Depends(get_db)
):
    result = await db.users.delete_one({"_id": oid(user_id)})
    return {"status": "ok", "count": result.deleted_count}


@router.get("/users/{user_id}/login-as")
async def login_as(
    user_id: str,
    request: Request,
    admin: dict = Depends(get_admin_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    target = await db.users.find_one({"_id": oid(user_id)})
    if not target:
        return {"status": "error", "msg": "User not found"}
    if target.get("is_admin"):
        return {"status": "error", "msg": "Cannot log into admin account"}

    login_user(request, target)
    return {"status": "ok"}


@router.get("/users/{user_id}/export")
async def export_user(
    user_id: str,
    admin: dict = Depends(get_admin_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    target = await db.users.find_one({"_id": oid(user_id)})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    export = await node_service.export_user_tree(db, target["username"])
    filename = f"{target['username']}-export.json"
    return JSONResponse(
        content=export,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/users/{user_id}/import")
async def import_user(
    request: Request,
    user_id: str,
    file: UploadFile = File(...),
    admin: dict = Depends(get_admin_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    target = await db.users.find_one({"_id": oid(user_id)})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    raw = await file.read()
    try:
        export = json.loads(raw)
    except json.JSONDecodeError:
        return RedirectResponse(base_url("/users?msg=Invalid import file"), status_code=303)

    if not isinstance(export, dict) or "nodes" not in export:
        return RedirectResponse(base_url("/users?msg=Invalid import file format"), status_code=303)

    count = await node_service.import_user_tree(db, export, target["username"])
    return RedirectResponse(
        base_url(f"/users?msg=Imported {count} node(s) for {target['username']}"), status_code=303
    )
