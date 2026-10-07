from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import auth, details, todos
from .config import settings
from .db import Base, engine
from .integrations import notion, outlook, slack

STATIC = Path(__file__).resolve().parent.parent / "static"

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
settings.validate()
# TODO: switch to Alembic migrations before the first schema change in production.
Base.metadata.create_all(engine)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await notion.startup()
    await slack.startup()
    yield
    await slack.shutdown()
    await notion.shutdown()


app = FastAPI(title="Andean Dashboard", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy",
                                "default-src 'self'; img-src 'self' data: https:; "
                                "frame-src https://www.figma.com https://embed.figma.com https://docs.google.com https://drive.google.com; "
                                "frame-ancestors 'none'; base-uri 'none'; form-action 'self' https://login.microsoftonline.com")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith(("/api", "/auth")):
        response.headers.setdefault("Cache-Control", "no-store")
    elif request.url.path.startswith("/static"):
        # Revalidate (cheap 304s via ETag) so a new deploy's JS/CSS is never mixed with stale files
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


# Added last so it wraps everything above and request.session is always available
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="andean_session",
    max_age=auth.REMEMBER_SECONDS,
    same_site="lax",
    https_only=settings.is_production,
)

app.include_router(auth.router)
app.include_router(todos.router)
app.include_router(details.router)
app.include_router(slack.router)
app.include_router(notion.router)
app.include_router(outlook.router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def dashboard(request: Request):
    if not auth.signed_in_id(request):
        return RedirectResponse("/login", status_code=302)
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/login")
def login_page(request: Request):
    if auth.signed_in_id(request):
        return RedirectResponse("/", status_code=302)
    return FileResponse(STATIC / "login.html")


@app.get("/auth/config")
def auth_config():
    """Tells the login page which buttons to show."""
    return {"microsoft": settings.microsoft_configured, "dev_login": settings.dev_login_enabled,
            "slack": settings.slack_configured, "notion": settings.notion_configured}
