"""급여 항목(PayrollEntry) 변경이력 기록.

- 호출부 트랜잭션에 묻어간다 — 여기서 직접 commit하지 않는다 (`services/access_log.log_access`와 같은 패턴).
- 기록하는 필드는 `TRACKED_FIELDS` 화이트리스트뿐이다. 주민번호·계좌번호·원문 텍스트·`anomaly_notes`는
  이력에 절대 들어가지 않는다(Employee 쪽 값이고, 여기 필드가 아니다).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, PayrollEntry, PayrollEntryChange, User

# 이력에 남기는 필드. 금액·세액·4대보험·소득유형·이름·지급일·근무일수·코드·직원 연결.
TRACKED_FIELDS: tuple[str, ...] = (
    "raw_name", "employee_id", "income_type", "business_type_code", "other_income_code",
    "total_amount", "salary_amount", "bonus_amount", "non_taxable",
    "meal_amount", "car_amount", "childcare_amount", "taxable", "necessary_expense",
    "national_pension", "health_insurance", "employment_insurance", "longterm_care",
    "income_tax", "local_tax", "student_loan", "settlement_insurance", "rent_support",
    "payment_date", "work_days",
)

ACTIONS = ("CREATE", "UPDATE", "DELETE", "RESTORE", "APPROVE", "UNAPPROVE", "PURGE")
SOURCES = ("manual", "collect", "portal", "carry_forward", "import", "fast_path", "system")


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def snapshot_values(entry: PayrollEntry) -> dict[str, Any]:
    """이력·원본 보존에 쓰는 필드 값만 JSON 직렬화 가능한 dict로 뽑는다."""
    return {name: _plain(getattr(entry, name, None)) for name in TRACKED_FIELDS}


def diff_values(
    before: dict[str, Any], after: dict[str, Any], manual_fields: set[str] | None = None
) -> dict[str, dict[str, Any]]:
    """바뀐 필드만 {필드: {"before", "after", "auto"?}}. manual_fields에 없는 변경은 자동 재계산으로 표시."""
    out: dict[str, dict[str, Any]] = {}
    for name in TRACKED_FIELDS:
        if before.get(name) != after.get(name):
            item: dict[str, Any] = {"before": before.get(name), "after": after.get(name)}
            if manual_fields is not None and name not in manual_fields:
                item["auto"] = True
            out[name] = item
    return out


async def record_patch(
    db: AsyncSession,
    entry: PayrollEntry,
    patch: dict[str, Any],
    before: dict[str, Any],
    was_approved: bool,
    was_deleted: bool,
    *,
    user: User,
    batch_id: str | None = None,
) -> bool:
    """PATCH 한 번을 이력으로 풀어 쓴다 — 삭제·복구, 값 변경, 승인·승인취소를 각각 한 행으로.

    값과 승인이 한 번에 바뀌면 UPDATE 다음에 APPROVE 두 행이 남는다. 기록한 행이 있으면 True.
    """
    after = snapshot_values(entry)
    changes = diff_values(before, after, {k for k in patch if k in TRACKED_FIELDS})
    reason = patch.get("edit_reason")
    recorded = False

    if "deleted" in patch and bool(patch["deleted"]) != was_deleted:
        if patch["deleted"]:
            await record_change(db, entry, "DELETE", user=user, reason=reason,
                                changes={"snapshot": before}, batch_id=batch_id)
        else:
            await record_change(db, entry, "RESTORE", user=user, reason=reason, batch_id=batch_id)
        recorded = True
    if changes:
        await record_change(db, entry, "UPDATE", user=user, reason=reason, changes=changes, batch_id=batch_id)
        recorded = True
    if "approved" in patch and bool(patch["approved"]) != was_approved:
        await record_change(db, entry, "APPROVE" if patch["approved"] else "UNAPPROVE",
                            user=user, batch_id=batch_id)
        recorded = True
    if not recorded and reason:  # 사유만 바꾼 경우
        await record_change(db, entry, "UPDATE", user=user, reason=reason, changes={}, batch_id=batch_id)
        recorded = True
    return recorded


async def record_change(
    db: AsyncSession,
    entry: PayrollEntry,
    action: str,
    *,
    user: User | None = None,
    source: str = "manual",
    reason: str | None = None,
    changes: dict | None = None,
    actor_label: str | None = None,
    batch_id: str | None = None,
) -> PayrollEntryChange:
    """이력 한 행을 추가한다 (commit은 호출부). user가 없으면(포털·카카오·시스템) actor_label로 표기."""
    assert action in ACTIONS and source in SOURCES, (action, source)
    if user is not None:
        tax_office_id = user.tax_office_id
        label = user.name
    else:
        tax_office_id = await db.scalar(select(Client.tax_office_id).where(Client.id == entry.client_id))
        label = actor_label
    row = PayrollEntryChange(
        tax_office_id=tax_office_id,
        monthly_filing_id=entry.monthly_filing_id,
        client_id=entry.client_id,
        entry_id=entry.id,
        employee_id=entry.employee_id,
        subject_name=(entry.raw_name or "")[:100],
        income_type=_plain(entry.income_type),
        action=action,
        changes=changes,
        reason=(reason or None),
        source=source,
        actor_user_id=user.id if user is not None else None,
        actor_label=(label or None),
        collection_event_id=entry.collection_event_id,
        batch_id=batch_id,
    )
    db.add(row)
    return row
