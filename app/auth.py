from fastapi import Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from passlib.context import CryptContext

from app.database import get_db
from app.models import oid

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def login_user(request: Request, user: dict) -> None:
    request.session["user_id"] = str(user["_id"])
    request.session["username"] = user["username"]
    request.session["domain"] = user["domain"]
    request.session["is_admin"] = bool(user.get("is_admin", False))


def logout_user(request: Request) -> None:
    request.session.clear()


async def get_optional_user(request: Request, db: AsyncIOMotorDatabase = Depends(get_db)) -> dict | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return await db.users.find_one({"_id": oid(user_id)})


async def get_current_user(user: dict | None = Depends(get_optional_user)) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="Please login")
    return user


async def get_admin_user(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
