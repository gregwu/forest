from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.auth import get_current_user, hash_password, login_user, logout_user, verify_password
from app.database import get_db
from app.templating import templates
from app.urls import url as base_url

router = APIRouter()


@router.get("/login")
async def login_page(request: Request, msg: str = "", url: str = "/index.html"):
    if request.session.get("username"):
        return templates.TemplateResponse(request, "login.html", {"msg": "", "url": url})
    return templates.TemplateResponse(request, "login.html", {"msg": msg, "url": url})


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    url: str = Form("/index.html"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    # `url` may be an app-internal (unprefixed) path forwarded from the login-redirect
    # handler, or already base-prefixed from the login form's hidden field. base_url()
    # is idempotent, so this normalizes either case to a browser-facing prefixed path.
    target = base_url(url)

    user = await db.users.find_one({"username": username})
    if not user or not verify_password(password, user["password_hash"]):
        return RedirectResponse(
            f"{base_url('/login')}?msg=Wrong Username or Password&url={target}", status_code=303
        )

    login_user(request, user)
    return RedirectResponse(target or base_url("/index.html"), status_code=303)


@router.get("/logout")
async def logout(request: Request):
    logout_user(request)
    return RedirectResponse(base_url("/login"), status_code=303)


@router.get("/register")
async def register_page(request: Request, msg: str = ""):
    return templates.TemplateResponse(request, "register.html", {"msg": msg})


@router.post("/register")
async def register_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    domain: str = Form(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    if not username or not password or not domain:
        return RedirectResponse(base_url("/register"), status_code=303)

    if await db.users.find_one({"username": username}):
        return RedirectResponse(base_url("/register?msg=username already exists"), status_code=303)

    if await db.users.find_one({"domain": domain}):
        return RedirectResponse(base_url("/register?msg=domain already exists"), status_code=303)

    await db.users.insert_one(
        {"username": username, "password_hash": hash_password(password), "domain": domain, "is_admin": False}
    )
    return RedirectResponse(base_url("/login?msg=Please login"), status_code=303)


@router.get("/forgot")
async def forgot_page(request: Request, msg: str = ""):
    return templates.TemplateResponse(request, "forgot.html", {"msg": msg})


@router.post("/forgot")
async def forgot_submit(request: Request, username: str = Form(...)):
    # No mail transport configured in this environment; direct the user to an admin-assisted reset.
    return RedirectResponse(
        base_url("/forgot?msg=Please contact an administrator to reset your password"), status_code=303
    )


@router.get("/user")
async def user_page(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(request, "user.html", {"msg": "", "user": user})


@router.get("/help")
async def help_page(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(request, "help.html", {"user": user})


@router.post("/user")
async def user_update(
    request: Request,
    oldpassword: str = Form(...),
    password: str = Form(...),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    if not verify_password(oldpassword, user["password_hash"]):
        return RedirectResponse(base_url("/login?msg=Wrong old password"), status_code=303)

    await db.users.update_one({"_id": user["_id"]}, {"$set": {"password_hash": hash_password(password)}})
    return RedirectResponse(base_url("/login?msg=Password updated"), status_code=303)
