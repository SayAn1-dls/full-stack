"""FastAPI application: `uvicorn app.main:app` (from backend/)."""

from __future__ import annotations

from fastapi import FastAPI

from app.wind.routes import router

app = FastAPI(
    title="Wind Intelligence API",
    version="1.0.0",
    description="Day-ahead wind forecast check on Elexon FUELHH (WIND) and WINDFOR data, January 2026.",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)
app.include_router(router)
