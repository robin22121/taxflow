import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings


# 앱 로거를 INFO로 설정 — 채널 발송 진단(stub/aligo/sendgrid)이 Render Logs에 보이도록
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="이지원천",
        version="0.1.0",
        debug=settings.app_debug,
        lifespan=lifespan,
    )

    origins = [settings.app_public_url]
    # auto-add www / non-www variant
    pub = settings.app_public_url
    if "://www." in pub:
        origins.append(pub.replace("://www.", "://"))
    elif "://" in pub:
        origins.append(pub.replace("://", "://www."))
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

    @app.get("/healthz/storage")
    async def healthz_storage() -> dict:
        """Storage diagnostic — Render Shell이나 브라우저에서 디스크 상태 확인용."""
        from pathlib import Path
        import os

        render_disk = Path("/data/uploads")
        local_disk = Path("data/uploads")

        def _dir_info(p: Path) -> dict:
            if not p.exists():
                return {"exists": False}
            try:
                files = list(p.rglob("*"))
                file_count = sum(1 for f in files if f.is_file())
                total_bytes = sum(f.stat().st_size for f in files if f.is_file())
            except Exception as e:
                return {"exists": True, "error": str(e)}
            return {
                "exists": True,
                "is_dir": p.is_dir(),
                "file_count": file_count,
                "total_bytes": total_bytes,
                "sample_files": [str(f.relative_to(p)) for f in files if f.is_file()][:10],
            }

        from app.services.storage import get_storage
        storage = get_storage()

        return {
            "active_storage": storage.name,
            "active_base": str(getattr(storage, "base", "n/a")),
            "render_disk_mount": _dir_info(render_disk),
            "local_fallback": _dir_info(local_disk),
            "cwd": os.getcwd(),
        }

    from app.api import register_routes

    register_routes(app)

    return app


app = create_app()
