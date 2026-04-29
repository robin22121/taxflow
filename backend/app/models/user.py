from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.tax_office import TaxOffice


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email_unique", "email", unique=True),)

    tax_office_id: Mapped[str] = mapped_column(ForeignKey("tax_offices.id"))
    email: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    tax_office: Mapped[TaxOffice] = relationship()
