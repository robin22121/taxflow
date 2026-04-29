from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import Base, IdMixin, TimestampMixin


class TaxOffice(Base, IdMixin, TimestampMixin):
    __tablename__ = "tax_offices"

    name: Mapped[str] = mapped_column(String(200))
    business_number: Mapped[str | None] = mapped_column(String(20))
    representative: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(40))

    def __repr__(self) -> str:
        return f"<TaxOffice {self.name}>"
