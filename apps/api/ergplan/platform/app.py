"""The FastAPI application. Routers are mounted per area; each stage adds its own."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from ..core.settings import get_settings
from ..db.base import session_scope
from .routers import cost, documents, intake, prices, regreader, rulebooks


def create_app() -> FastAPI:
    app = FastAPI(title="jouleWise | ergPLAN API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[get_settings().ergplan_public_url, "http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, Any]:
        with session_scope() as s:
            db = s.execute(text("select version()")).scalar_one()
            rev = s.execute(text("select version_num from alembic_version")).scalar_one_or_none()
        return {"status": "ok", "database": str(db).split(" on ")[0], "migration": rev}

    app.include_router(documents.router)
    app.include_router(rulebooks.router)
    app.include_router(regreader.router)
    app.include_router(intake.router)
    app.include_router(prices.router)
    app.include_router(cost.router)
    return app


app = create_app()
