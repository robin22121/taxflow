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
    cors_extra_origins: str = ""  # comma-separated additional CORS origins

    database_url: str = "sqlite+aiosqlite:///./taxflow.db"

    @property
    def async_database_url(self) -> str:
        """Render provides postgres:// but SQLAlchemy needs postgresql+asyncpg://."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    redis_url: str = "redis://localhost:6379/0"

    # ── AI 프로바이더 ────────────────────────────────────
    ai_provider: str = "gemini"  # gemini | anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    rrn_encryption_key: str = ""

    jwt_secret: str = "change-me-32-bytes"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_min: int = 60
    jwt_refresh_ttl_days: int = 14

    # ── 서버 관리자(슈퍼어드민) 시드 ──────────────────────────
    # email/password 둘 다 설정돼야 기동 시 슈퍼어드민 계정을 시드한다.
    superadmin_email: str = ""
    superadmin_password: str = ""
    superadmin_name: str = "서버 관리자"

    # ── 메시징 채널 ─────────────────────────────────────────
    # alimtalk 우선순위: nhn_cloud > aligo > stub
    kakao_alimtalk_provider: str = "stub"  # stub | aligo | nhn_cloud
    aligo_api_key: str = ""
    aligo_user_id: str = ""
    aligo_sender_key: str = ""
    nhn_cloud_app_key: str = ""
    nhn_cloud_secret_key: str = ""
    nhn_cloud_sender_key: str = ""

    # SMS — 알림톡 fallback. ALIGO_API_KEY/USER_ID는 알림톡과 공유.
    sms_provider: str = "stub"  # stub | aligo
    aligo_sms_sender: str = ""   # SMS 발신번호 (Aligo 사전 등록 필요)

    # email 우선순위: resend > ncp_outbound > sendgrid > stub
    email_provider: str = "auto"  # auto | resend | ncp_outbound | sendgrid | stub
    resend_api_key: str = ""
    resend_from_email: str = ""  # 예: onboarding@resend.dev (테스트) 또는 noreply@yourdomain.com
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = ""
    ncp_outbound_access_key: str = ""
    ncp_outbound_secret_key: str = ""
    ncp_outbound_sender_address: str = ""
    ncp_outbound_sender_name: str = "TaxFlow AI"

    # ── 웹훅 인증 ──────────────────────────────────────────
    kakao_webhook_secret: str = ""  # 카카오 오픈빌더 스킬 서버 시크릿 키
    sendgrid_webhook_secret: str = ""  # SendGrid Inbound Parse Basic Auth password

    # ── NCP Object Storage ────────────────────────────────
    ncp_object_storage_endpoint: str = "https://kr.object.ncloudstorage.com"
    ncp_object_storage_region: str = "kr-standard"
    ncp_object_storage_access_key: str = ""
    ncp_object_storage_secret_key: str = ""
    ncp_object_storage_bucket: str = "taxflow-uploads"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.app_env != "dev":
        insecure = []
        if s.app_secret_key.startswith("change-me"):
            insecure.append("APP_SECRET_KEY")
        if s.jwt_secret.startswith("change-me"):
            insecure.append("JWT_SECRET")
        if not s.rrn_encryption_key:
            insecure.append("RRN_ENCRYPTION_KEY")
        if insecure:
            raise RuntimeError(
                f"Production-unsafe default secrets detected: {', '.join(insecure)}. "
                "Set proper values in environment variables."
            )
    return s
