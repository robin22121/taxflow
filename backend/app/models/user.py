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

    tax_office: Mapped[TaxOffice | None] = relationship()
