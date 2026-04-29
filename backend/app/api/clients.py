"""Client (거래처) + Employee endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models import Client, Employee, EmploymentStatus, User
from app.schemas.clients import ClientCreate, ClientOut, EmployeeCreate, EmployeeOut
from app.services.crypto import encrypt_rrn, mask_rrn

router = APIRouter()


@router.get("", response_model=list[ClientOut])
async def list_clients(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Client]:
    rows = (
        await db.execute(
            select(Client).where(Client.tax_office_id == user.tax_office_id).order_by(Client.business_name)
        )
    ).scalars().all()
    return list(rows)


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Client:
    client = Client(
        tax_office_id=user.tax_office_id,
        business_name=payload.business_name,
        business_number=payload.business_number,
        representative=payload.representative,
        contact_phone=payload.contact_phone,
        contact_email=str(payload.contact_email) if payload.contact_email else None,
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return client


@router.get("/{client_id}/employees", response_model=list[EmployeeOut])
async def list_employees(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Employee]:
    client = await db.get(Client, client_id)
    if not client or client.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    rows = (
        await db.execute(select(Employee).where(Employee.client_id == client_id).order_by(Employee.name))
    ).scalars().all()
    return list(rows)


@router.post("/{client_id}/employees", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
async def create_employee(
    client_id: str,
    payload: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Employee:
    client = await db.get(Client, client_id)
    if not client or client.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    rrn_encrypted = encrypt_rrn(payload.rrn) if payload.rrn else None
    rrn_last4 = mask_rrn(payload.rrn).split("-")[-1][:4] if payload.rrn else None
    emp = Employee(
        client_id=client_id,
        name=payload.name,
        rrn_encrypted=rrn_encrypted,
        rrn_last4=rrn_last4,
        employee_code=payload.employee_code,
        hired_at=payload.hired_at,
        status=EmploymentStatus.ACTIVE if payload.rrn else EmploymentStatus.PENDING,
    )
    db.add(emp)
    await db.commit()
    await db.refresh(emp)
    return emp
