import enum

from sqlalchemy import Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.client import Client
from app.models.user import User


class MessageSender(str, enum.Enum):
    OWNER = "OWNER"
    STAFF = "STAFF"


class PortalMessage(Base, IdMixin, TimestampMixin):
    """사업주 포털 메시지 — 자료 제출 커뮤니케이션 채널 (plan/12-owner-portal.md §3.8, §5.5).

    AI가 아닌 세무사무소 직원이 직접 응대한다. 알림은 의도적으로 두지 않는다 —
    급한 연락은 기존 카톡·전화로 한다(§3.8). ``MonthlyFiling``이 아니라 ``Client``
    하위다 — §5.2 ``EmployeeChangeRequest``와 같은 이유로 월/신고 세션과 무관하게
    발생하는 이벤트이기 때문이다.
    """

    __tablename__ = "portal_messages"
    __table_args__ = (
        Index("ix_portal_messages_client_created", "client_id", "created_at"),
    )

    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    sender_type: Mapped[MessageSender] = mapped_column(
        Enum(MessageSender, native_enum=False, length=10)
    )
    # STAFF 발신일 때만 — 대화창 상단에 응대한 직원 이름을 표시하는 데 쓴다.
    staff_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str | None] = mapped_column(Text)
    attachment_url: Mapped[str | None] = mapped_column(String(500))
    attachment_name: Mapped[str | None] = mapped_column(String(255))

    client: Mapped[Client] = relationship()
    staff_user: Mapped[User | None] = relationship()
