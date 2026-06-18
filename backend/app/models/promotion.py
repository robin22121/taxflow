from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import Base, IdMixin, TimestampMixin


class Promotion(Base, IdMixin, TimestampMixin):
    """사무소에 부여된 프로모션 이력 — 서버 관리자가 부여/관리."""

    __tablename__ = "promotions"
    __table_args__ = (Index("ix_promotions_office", "tax_office_id"),)

    tax_office_id: Mapped[str] = mapped_column(ForeignKey("tax_offices.id"))
    name: Mapped[str] = mapped_column(String(200))            # 프로모션명
    discount: Mapped[str | None] = mapped_column(String(100))  # 할인 내용 (예: "30%", "3개월 무료")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    memo: Mapped[str | None] = mapped_column(String(500))
    granted_by: Mapped[str | None] = mapped_column(String(32))  # 부여한 슈퍼어드민 user id
