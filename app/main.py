"""FastAPI application entrypoint. Serves the API and the static frontend."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes import router
from app.logging_config import get_logger, setup_logging

setup_logging()
log = get_logger("main")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("ArcVision backend starting up.")
    yield


app = FastAPI(title="ArcVision", version="0.1.0", lifespan=lifespan)
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")


@app.get("/")
async def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))
