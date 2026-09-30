from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.tax_office import TaxOffice


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email_unique", "email", unique=True),)

    # 서버 관리자(슈퍼어드민)는 특정 사무소에 속하지 않으므로 nullable
    tax_office_id: Mapped[str | None] = mapped_column(ForeignKey("tax_offices.id"), nullable=True)
    email: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)  # 사무소 관리자
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)  # 서버 관리자
    # 사무소 내부 역할·권한 (plan/14-accounts-permissions.md §3, §3.2, §6.5 — 2026-09-30)
    # role: OWNER(대표) | STAFF(담당직원). is_admin과 별개 축으로 당장은 함께 유지, is_admin은 백필 소스로만 쓴다.
    role: Mapped[str] = mapped_column(String(20), default="OWNER", server_default="OWNER")
    # 사무소 내부 개인 식별 코드(로그인 시 아이디(사업자번호)+코드+비밀번호 3필드 중 하나) — 대표=a, 이후 직원은 b,c,d… 순차 부여.
    # 지금은 백필만 하고 로그인 엔드포인트는 아직 이 필드를 쓰지 않는다 — 프론트/로그인 API 변경은 후속 작업.
    login_code: Mapped[str | None] = mapped_column(String(1), nullable=True)
    # STAFF 전용 쓰기 권한 — OWNER는 항상 true로 취급(백엔드가 role로 강제, 이 값은 참고용).
    can_write: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    tax_office: Mapped[TaxOffice | None] = relationship()
