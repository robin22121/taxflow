from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.tax_office import TaxOffice


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"
    # 사무소 내 직원계정은 대표와 같은 email(사업자번호)을 공유하고 login_code로만
    # 구분된다(plan/14 §6.5) — 전역 email 유일성은 (email, login_code) 조합 유일성으로 대체.
    # superadmin의 login_code는 NULL이며, NULL끼리는 유니크 제약에서 충돌하지 않는다.
    __table_args__ = (Index("ix_users_email_login_code_unique", "email", "login_code", unique=True),)

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
    login_code: Mapped[str | None] = mapped_column(String(1), nullable=True)
    # STAFF 전용 쓰기 권한 — OWNER는 항상 true로 취급(백엔드가 role로 강제, 이 값은 참고용).
    can_write: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # 최초 로그인 시 비밀번호 변경 강제 (plan/14 §6.2) — OWNER가 직원 등록 시 True로 생성.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # 로그인 시도 제한 (plan/14 §8 "일정 횟수 인증 실패 시 접근 제한") — portal PIN 잠금과 같은 패턴.
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tax_office: Mapped[TaxOffice | None] = relationship()
