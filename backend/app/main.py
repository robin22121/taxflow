from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TaxFlow AI",
        version="0.1.0",
        debug=settings.app_debug,
        lifespan=lifespan,
    )

    origins = [settings.app_public_url]
    if settings.cors_extra_origins:
        origins.extend(settings.cors_extra_origins.split(","))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    from app.api import register_routes

    register_routes(app)

    return app


app = create_app()
