"""접속·접근 기록 — plan/14-accounts-permissions.md §8.1."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccessLog


async def log_access(
    db: AsyncSession,
    action: str,
    *,
    user_id: str | None = None,
    tax_office_id: str | None = None,
    ip: str | None = None,
    client_id: str | None = None,
    subject_employee_id: str | None = None,
    endpoint: str | None = None,
) -> None:
    """호출부에서 db.commit()할 때 함께 커밋된다 — 여기서 별도 commit하지 않는다."""
    db.add(
        AccessLog(
            user_id=user_id,
            tax_office_id=tax_office_id,
            ip=ip,
            action=action,
            client_id=client_id,
            subject_employee_id=subject_employee_id,
            endpoint=endpoint,
        )
    )
