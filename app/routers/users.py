from fastapi import APIRouter, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.auth import get_current_user, login_user
from app.database import get_db
from app.models import oid
from app.templating import templates

router = APIRouter()


@router.get("/users")
async def users_page(request: Request, user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
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
    return templates.TemplateResponse(request, "users.html", {"users": users, "current_user": user})


@router.post("/users/{user_id}/role")
async def change_role(user_id: str, is_admin: bool, db: AsyncIOMotorDatabase = Depends(get_db)):
    await db.users.update_one({"_id": oid(user_id)}, {"$set": {"is_admin": is_admin}})
    return {"status": "ok"}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    result = await db.users.delete_one({"_id": oid(user_id)})
    return {"status": "ok", "count": result.deleted_count}


@router.get("/users/{user_id}/login-as")
async def login_as(user_id: str, request: Request, admin: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    if not admin.get("is_admin"):
        return {"status": "error", "msg": "Admin access required"}

    target = await db.users.find_one({"_id": oid(user_id)})
    if not target:
        return {"status": "error", "msg": "User not found"}
    if target.get("is_admin"):
        return {"status": "error", "msg": "Cannot log into admin account"}

    login_user(request, target)
    return {"status": "ok"}
