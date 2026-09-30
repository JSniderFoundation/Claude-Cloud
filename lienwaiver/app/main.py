from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import LoginRequired, bootstrap_admin
from .config import settings
from .db import SessionLocal, init_db
from .routers import auth, portal, queue, records, settings as settings_router, waivers
from .services import jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings.pdf_dir.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        bootstrap_admin(db)
    finally:
        db.close()
    task = asyncio.create_task(jobs.scheduler(SessionLocal))
    yield
    task.cancel()


app = FastAPI(title="Lien Waivers", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax", https_only=settings.base_url.startswith("https"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")


@app.exception_handler(LoginRequired)
async def _login_redirect(request: Request, exc: LoginRequired):
    return RedirectResponse(exc.headers["Location"], status_code=303)


@app.get("/health")
def health():
    return {"ok": True}


app.include_router(auth.router)
app.include_router(portal.router)
app.include_router(queue.router)
app.include_router(waivers.router)
app.include_router(records.router)
app.include_router(settings_router.router)
