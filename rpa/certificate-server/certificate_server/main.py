"""FastAPI 앱 진입점. 실행: uvicorn certificate_server.main:app --port 8100 --host 0.0.0.0"""

from __future__ import annotations

from fastapi import FastAPI

from certificate_server.db import init_db
from certificate_server.routes_agent import router as agent_router
from certificate_server.routes_user import router as user_router


def create_app() -> FastAPI:
    app = FastAPI(title="Certificate Server (Phase 1.5 sim)")
    init_db()
    app.include_router(user_router)
    app.include_router(agent_router)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    return app


app = create_app()
