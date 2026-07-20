from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import close_client, ensure_indexes
from app.routers import auth as auth_router
from app.routers import nodes as nodes_router
from app.routers import publish as publish_router
from app.routers import users as users_router
from app.urls import url as base_url


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    yield
    await close_client()


app = FastAPI(title="Forest", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie,
    path=settings.base_path or "/",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/pages", StaticFiles(directory=settings.pages_dir, check_dir=False), name="pages")

app.include_router(auth_router.router)
app.include_router(nodes_router.router)
app.include_router(publish_router.router)
app.include_router(users_router.router)


@app.exception_handler(HTTPException)
async def auth_redirect_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401 and not request.url.path.startswith("/api/"):
        target = request.url.path
        if request.url.query:
            target += f"?{request.url.query}"
        return RedirectResponse(f"{base_url('/login')}?msg=Please login&url={target}", status_code=303)
    return JSONResponse(status_code=exc.status_code, content={"status": "error", "msg": exc.detail})
