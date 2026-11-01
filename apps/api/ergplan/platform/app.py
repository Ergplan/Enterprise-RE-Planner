"""The FastAPI application. Routers are mounted per area; each stage adds its own."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.base import RequestResponseEndpoint

from ..core.settings import get_settings
from ..db.base import session_scope
from .auth import guard, production
from .routers import auth as auth_routes
from .routers import cost, documents, intake, landed, plan, prices, regreader, rulebooks, runs, settle, voice

log = logging.getLogger("ergplan.app")


def create_app() -> FastAPI:
    app = FastAPI(title="jouleWise | ergPLAN API", version="0.1.0", dependencies=[Depends(guard)])
    origins = [get_settings().ergplan_public_url]
    if production() and not origins[0].startswith("https://"):
        # a LAN server: the session cookie cannot be Secure and travels unencrypted on the network
        log.warning("ERGPLAN_PUBLIC_URL is not https in production (LAN use only): %s", origins[0])
    if not production():
        origins += ["http://localhost:3000", "http://127.0.0.1:3000"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-Ergplan-Actor", "X-Ergplan-Role"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=()")
        if production():
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.get("/health", tags=["health"])
    def health() -> dict[str, Any]:
        with session_scope() as s:
            db = s.execute(text("select version()")).scalar_one()
            rev = s.execute(text("select version_num from alembic_version")).scalar_one_or_none()
        return {"status": "ok", "database": str(db).split(" on ")[0], "migration": rev}

    app.include_router(auth_routes.router)
    app.include_router(documents.router)
    app.include_router(landed.router)  # before rulebooks: /rulebooks/limits
    app.include_router(rulebooks.router)
    app.include_router(regreader.router)
    app.include_router(intake.router)
    app.include_router(prices.router)
    app.include_router(cost.router)
    app.include_router(settle.router)
    app.include_router(runs.router)
    app.include_router(plan.router)
    app.include_router(voice.router)
    return app


app = create_app()
