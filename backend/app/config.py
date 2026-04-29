from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "dev"
    app_debug: bool = True
    app_secret_key: str = "change-me-in-prod-32-bytes-min-xxxxxxxx"
    app_base_url: str = "http://localhost:8000"
    app_public_url: str = "http://localhost:3000"

    database_url: str = "sqlite+aiosqlite:///./taxflow.db"
    redis_url: str = "redis://localhost:6379/0"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"

    rrn_encryption_key: str = ""

    jwt_secret: str = "change-me-32-bytes"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_min: int = 60
    jwt_refresh_ttl_days: int = 14

    # ── 메시징 채널 ─────────────────────────────────────────
    # alimtalk 우선순위: nhn_cloud > aligo > stub
    kakao_alimtalk_provider: str = "stub"  # stub | aligo | nhn_cloud
    aligo_api_key: str = ""
    aligo_user_id: str = ""
    aligo_sender_key: str = ""
    nhn_cloud_app_key: str = ""
    nhn_cloud_secret_key: str = ""
    nhn_cloud_sender_key: str = ""

    # email 우선순위: ncp_outbound > sendgrid > stub
    email_provider: str = "auto"  # auto | ncp_outbound | sendgrid | stub
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = ""
    ncp_outbound_access_key: str = ""
    ncp_outbound_secret_key: str = ""
    ncp_outbound_sender_address: str = ""
    ncp_outbound_sender_name: str = "TaxFlow AI"

    # ── STT ───────────────────────────────────────────────
    stt_provider: str = "stub"  # stub | clova | whisper
    clova_invoke_url: str = ""
    clova_secret_key: str = ""

    # ── NCP Object Storage ────────────────────────────────
    ncp_object_storage_endpoint: str = "https://kr.object.ncloudstorage.com"
    ncp_object_storage_region: str = "kr-standard"
    ncp_object_storage_access_key: str = ""
    ncp_object_storage_secret_key: str = ""
    ncp_object_storage_bucket: str = "taxflow-uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()
