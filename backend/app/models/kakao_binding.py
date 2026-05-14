from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.tax_office import TaxOffice


class KakaoUserBinding(Base, IdMixin, TimestampMixin):
    """카카오톡 유저(plusfriendUserKey) ↔ 세무사사무소 바인딩.

    세무사 직원이 카카오 채널에서 처음 메시지를 보내면 사무소 코드를 입력받고,
    이후부터는 자동으로 해당 사무소의 거래처에서만 매칭한다.
    """

    __tablename__ = "kakao_user_bindings"
    __table_args__ = (
        Index("ix_kakao_binding_key", "plusfriend_key", unique=True),
    )

    plusfriend_key: Mapped[str] = mapped_column(String(200))
    tax_office_id: Mapped[str] = mapped_column(ForeignKey("tax_offices.id"))

    tax_office: Mapped[TaxOffice] = relationship()
