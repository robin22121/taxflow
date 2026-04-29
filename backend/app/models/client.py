from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.tax_office import TaxOffice


class Client(Base, IdMixin, TimestampMixin):
    """거래처 — 세무사사무소가 담당하는 사업자."""

    __tablename__ = "clients"
    __table_args__ = (
        Index("ix_clients_tax_office", "tax_office_id"),
    )

    tax_office_id: Mapped[str] = mapped_column(ForeignKey("tax_offices.id"))
    business_name: Mapped[str] = mapped_column(String(200))
    business_number: Mapped[str | None] = mapped_column(String(20))
    representative: Mapped[str | None] = mapped_column(String(100))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    contact_email: Mapped[str | None] = mapped_column(String(200))
    kakao_channel_id: Mapped[str | None] = mapped_column(String(100))

    tax_office: Mapped[TaxOffice] = relationship()
