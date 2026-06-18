from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import Base, IdMixin, TimestampMixin


class BetaSignup(Base, IdMixin, TimestampMixin):
    """베타/얼리버드 신청 — 랜딩 페이지 가입 폼에서 수집한 세무사사무소 정보."""

    __tablename__ = "beta_signups"

    office_name: Mapped[str] = mapped_column(String(200))  # 사무소명
    contact_name: Mapped[str] = mapped_column(String(100))  # 담당자명
    phone: Mapped[str] = mapped_column(String(40))  # 연락처
    email: Mapped[str | None] = mapped_column(String(200))
    employee_count: Mapped[int | None] = mapped_column(Integer)  # 사무소 직원 수
    client_count: Mapped[int | None] = mapped_column(Integer)  # 수임 거래처 수
    current_software: Mapped[str | None] = mapped_column(String(100))  # 현재 사용 SW (더존/세무사랑 등)
    note: Mapped[str | None] = mapped_column(String(1000))
    # 가입 시점 기준 자동 판정 트랙: "beta" | "earlybird" | "general"
    track: Mapped[str] = mapped_column(String(20), default="general")
