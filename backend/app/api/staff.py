"""직원계정 관리 — 등록/변경 (plan/14-accounts-permissions.md §6.6.1). 대표(OWNER)만 접근."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_owner
from app.core.security import hash_password
from app.models import Client, ClientAssignmentHistory, TaxOffice, User
from app.schemas.staff import StaffCreate, StaffOut, StaffUpdate

router = APIRouter()


async def _next_login_code(db: AsyncSession, tax_office_id: str) -> str:
    """사무소 내 다음 빈 코드 — 대표=a, 이후 등록 순서대로 b,c,d… (plan/14 §6.5, 결번 유지)."""
    codes = (
        await db.execute(
            select(User.login_code).where(
                User.tax_office_id == tax_office_id, User.login_code.is_not(None)
            )
        )
    ).scalars().all()
    next_ord = max((ord(c) for c in codes if c), default=ord("a") - 1) + 1
    if next_ord > ord("z"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "직원계정 코드(a~z)를 모두 사용했습니다")
    return chr(next_ord)


async def _with_assigned_counts(db: AsyncSession, users: list[User]) -> list[StaffOut]:
    counts = dict(
        (
            await db.execute(
                select(Client.assigned_user_id, func.count(Client.id))
                .where(Client.assigned_user_id.in_([u.id for u in users]))
                .group_by(Client.assigned_user_id)
            )
        ).all()
    )
    return [
        StaffOut(
            id=u.id,
            name=u.name,
            login_code=u.login_code,
            role=u.role,
            can_write=u.can_write,
            is_active=u.is_active,
            assigned_client_count=counts.get(u.id, 0),
        )
        for u in users
    ]


@router.get("", response_model=list[StaffOut])
async def list_staff(
    db: AsyncSession = Depends(get_db),
    owner: User = Depends(require_owner),
) -> list[StaffOut]:
    users = (
        await db.execute(
            select(User)
            .where(User.tax_office_id == owner.tax_office_id)
            .order_by(User.login_code)
        )
    ).scalars().all()
    return await _with_assigned_counts(db, list(users))


@router.post("", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
async def create_staff(
    payload: StaffCreate,
    db: AsyncSession = Depends(get_db),
    owner: User = Depends(require_owner),
) -> StaffOut:
    office = await db.get(TaxOffice, owner.tax_office_id)
    if office is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사무소를 찾을 수 없습니다")

    login_code = await _next_login_code(db, owner.tax_office_id)
    staff = User(
        tax_office_id=owner.tax_office_id,
        email=office.business_number,  # 사무소 공용 아이디 — 대표와 동일 (plan/14 §6.5)
        password_hash=hash_password(payload.password),
        name=payload.name,
        role="STAFF",
        login_code=login_code,
        can_write=payload.can_write,
    )
    db.add(staff)
    await db.commit()
    await db.refresh(staff)
    return StaffOut.model_validate(staff, from_attributes=True)


@router.patch("/{user_id}", response_model=StaffOut)
async def update_staff(
    user_id: str,
    payload: StaffUpdate,
    db: AsyncSession = Depends(get_db),
    owner: User = Depends(require_owner),
) -> StaffOut:
    staff = await db.get(User, user_id)
    if staff is None or staff.tax_office_id != owner.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "직원 계정을 찾을 수 없습니다")
    if staff.role == "OWNER" and payload.is_active is False:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "대표 계정은 비활성화할 수 없습니다")

    if payload.name is not None:
        staff.name = payload.name
    if payload.can_write is not None:
        staff.can_write = payload.can_write
    if payload.is_active is not None:
        staff.is_active = payload.is_active

    # 비활성화 즉시 담당 거래처 전부 미배정 전환 (plan/14 §6.3)
    if payload.is_active is False:
        assigned = (
            await db.execute(select(Client).where(Client.assigned_user_id == staff.id))
        ).scalars().all()
        for client in assigned:
            db.add(
                ClientAssignmentHistory(
                    client_id=client.id,
                    from_user_id=staff.id,
                    to_user_id=None,
                    changed_by=owner.id,
                )
            )
            client.assigned_user_id = None

    await db.commit()
    await db.refresh(staff)
    return await _one_with_count(db, staff)


async def _one_with_count(db: AsyncSession, staff: User) -> StaffOut:
    result = await _with_assigned_counts(db, [staff])
    return result[0]
