"""증명원 발급 — 상단 메뉴 팝업·증명발급 에이전트·고객 다운로드 링크 (plan/17 §4-6·§4-9).

사용자   GET  /catalog                       증명원 목록 (탭·준비중 여부)
        POST /issue-requests                 발급 요청 → rpa_jobs 1건 + 증명원별 행
        GET  /jobs/{job_id}                  요청 진행 상황 (팝업 폴링)
        GET  /issues/{id}/file               서버 사본 미리보기 (30일 이내)
        POST /jobs/{job_id}/open-folder      [폴더 열어 확인] — 에이전트 PC 에서 탐색기 열기
        POST /jobs/{job_id}/deliver          문자·알림톡 발송 (폴더 확인이 먼저)
에이전트 POST /agent/claim                    증명원 작업 1건 가져가기 (위하고 claim 과 분리)
        POST /agent/issues/{id}/file         발급본 업로드 (원본 경로 함께)
        POST /agent/issues/{id}/fail         개별 증명원 실패
        POST /agent/jobs/{job_id}/finish     요청 전체 종료
        GET  /agent/folder-requests          폴더 열기 요청 가져가기
        GET  /agent/issues/{id}/file         서버에서 만든 증명서(직원용) 내려받기 → 지정 폴더 저장
        POST /agent/issues/{id}/folder-opened  (내려받았으면 저장 경로 함께)
공개     GET  /api/v1/public/certificates/{token}   고객 다운로드 (30일)
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.rpa import RUNNING_TIMEOUT, _as_utc, _finish, _office_id, _utcnow, get_current_agent
from app.channels.alimtalk import get_alimtalk_channel
from app.channels.base import MessageRecipient
from app.channels.sms import get_sms_channel
from app.config import get_settings
from app.core.deps import get_current_user, get_db
from app.models import (
    CertificateIssue,
    CertificateStatus,
    Client,
    Employee,
    RpaAgent,
    RpaJob,
    RpaJobKind,
    RpaJobStatus,
    TaxOffice,
    User,
)
from app.schemas.rpa import RpaJobOut
from app.services.certificates import CATALOG, CATALOG_BY_CODE, RETENTION, delivery_body
from app.services.crypto import decrypt_rrn, mask_rrn
from app.services.employee_certificates import CertificateDataError, CertificateInput, render_pdf
from app.services.storage import get_storage

router = APIRouter()
public_router = APIRouter()

ALIMTALK_TEMPLATE = "CERT_ISSUED"  # 카카오 심사 전 — stub 에서만 동작 (plan/13)


# --- 스키마 --------------------------------------------------------------


class CatalogItem(BaseModel):
    code: str
    category: str
    title: str
    available: bool
    period: bool = False  # 기간 입력 필요 → 최근 1·3·5년
    note: str | None = None  # 발급 대상 제한 안내


class IssueRequestIn(BaseModel):
    client_id: str
    cert_types: list[str] = Field(min_length=1, max_length=20)
    rrn_disclosed: bool = False
    period_years: Literal[1, 3, 5] = 1  # 기간 있는 증명원에만 적용 (PERIOD_YEARS)
    employee_ids: list[str] = Field(default_factory=list, max_length=100)  # 직원용 증명서 대상
    purpose: str | None = Field(default=None, max_length=50)  # 직원용 증명서 '용도' 칸


class CertificateIssueOut(BaseModel):
    id: str
    client_id: str
    rpa_job_id: str
    employee_id: str | None
    cert_type: str
    title: str
    options: dict | None
    status: str
    business_number: str | None
    business_name: str
    issued_at: datetime | None
    local_path: str | None
    file_name: str | None
    has_file: bool
    expires_at: datetime | None
    failure_reason: str | None
    folder_open_requested_at: datetime | None
    folder_opened_at: datetime | None
    deliveries: list[dict] | None
    created_at: datetime

    @classmethod
    def of(cls, issue: CertificateIssue) -> CertificateIssueOut:
        return cls(
            **{k: getattr(issue, k) for k in cls.model_fields if k != "has_file"},
            has_file=issue.file_key is not None,
        )


class CertificateJobOut(BaseModel):
    job: RpaJobOut
    issues: list[CertificateIssueOut]


class AgentClaimOut(BaseModel):
    job: RpaJobOut | None
    issues: list[CertificateIssueOut] = []


class FailIn(BaseModel):
    reason: str = Field(max_length=2000)


class FinishIn(BaseModel):
    status: Literal["SUCCEEDED", "FAILED"]
    message: str | None = Field(default=None, max_length=2000)


class FolderOpenedIn(BaseModel):
    local_path: str | None = Field(default=None, max_length=500)  # 서버 생성분을 내려받아 저장한 경로


class DeliverIn(BaseModel):
    channel: Literal["sms", "alimtalk"]
    phone: str | None = Field(default=None, max_length=40)  # 비우면 거래처 담당자 연락처


class DeliverOut(BaseModel):
    accepted: bool
    channel: str
    to: str
    body: str
    error: str | None = None


# --- 공통 ----------------------------------------------------------------


async def _purge_expired(db: AsyncSession, issues: list[CertificateIssue]) -> None:
    """보관기간(30일)이 지난 서버 사본을 지운다. 원본은 에이전트 PC 폴더에 남는다."""
    now = _utcnow()
    storage = None
    for issue in issues:
        if issue.file_key and issue.expires_at and _as_utc(issue.expires_at) <= now:
            storage = storage or get_storage()
            storage.delete_object(issue.file_key)
            issue.file_key = None
            issue.download_token = None
    await db.commit()


async def _job_issues(db: AsyncSession, job_id: str) -> list[CertificateIssue]:
    rows = await db.execute(
        select(CertificateIssue).where(CertificateIssue.rpa_job_id == job_id).order_by(CertificateIssue.created_at)
    )
    return list(rows.scalars().all())


async def _user_job(db: AsyncSession, user: User, job_id: str) -> RpaJob:
    job = await db.get(RpaJob, job_id)
    if not job or job.tax_office_id != _office_id(user) or job.kind != RpaJobKind.CERTIFICATE_ISSUE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "증명원 발급 요청을 찾을 수 없습니다")
    return job


async def _job_out(db: AsyncSession, job: RpaJob) -> CertificateJobOut:
    issues = await _job_issues(db, job.id)
    await _purge_expired(db, issues)
    await db.refresh(job)
    return CertificateJobOut(
        job=RpaJobOut.model_validate(job), issues=[CertificateIssueOut.of(i) for i in issues]
    )


# --- 사용자 --------------------------------------------------------------


@router.get("/catalog", response_model=list[CatalogItem])
async def catalog(_: User = Depends(get_current_user)) -> list[dict]:
    return CATALOG


@router.post("/issue-requests", response_model=CertificateJobOut, status_code=status.HTTP_201_CREATED)
async def create_issue_request(
    payload: IssueRequestIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CertificateJobOut:
    office_id = _office_id(user)
    client = await db.get(Client, payload.client_id)
    if client is None or client.tax_office_id != office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "거래처를 찾을 수 없습니다")

    codes = list(dict.fromkeys(payload.cert_types))  # 중복 제거, 순서 유지
    for code in codes:
        item = CATALOG_BY_CODE.get(code)
        if item is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"알 수 없는 증명원: {code}")
        if not item["available"]:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{item['title']}은(는) 아직 준비중입니다")
    employee_codes = [c for c in codes if CATALOG_BY_CODE[c]["category"] == "EMPLOYEE"]
    if employee_codes:
        if len(employee_codes) != len(codes):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "직원용 증명서는 홈택스 증명원과 따로 요청하세요"
            )
        return await _issue_employee_certificates(db, user, client, codes, payload)

    job = RpaJob(
        tax_office_id=office_id,
        kind=RpaJobKind.CERTIFICATE_ISSUE,
        client_id=client.id,
        business_number=(client.business_number or "").strip(),
        business_name=client.business_name,
        requested_by_user_id=user.id,
        step_progress={code: "pending" for code in codes},
    )
    db.add(job)
    await db.flush()
    for code in codes:
        db.add(
            CertificateIssue(
                tax_office_id=office_id,
                client_id=client.id,
                requested_by_user_id=user.id,
                rpa_job_id=job.id,
                cert_type=code,
                title=CATALOG_BY_CODE[code]["title"],
                options={
                    "rrn_disclosed": payload.rrn_disclosed,
                    **({"period_years": payload.period_years} if CATALOG_BY_CODE[code].get("period") else {}),
                },
                business_number=job.business_number or None,
                business_name=client.business_name,
            )
        )
    await db.commit()
    return await _job_out(db, job)


async def _issue_employee_certificates(
    db: AsyncSession, user: User, client: Client, codes: list[str], payload: IssueRequestIn
) -> CertificateJobOut:
    """직원용 증명서는 서버가 바로 만든다 — 에이전트 대기 없이 요청 즉시 완료.

    원본 폴더 저장은 [폴더 열어 확인] 때 에이전트가 서버 사본을 내려받아 한다.
    """
    employee_ids = list(dict.fromkeys(payload.employee_ids))
    if not employee_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "증명서를 발급할 직원을 선택하세요")
    employees = (
        await db.execute(select(Employee).where(Employee.id.in_(employee_ids), Employee.client_id == client.id))
    ).scalars().all()
    if len(employees) != len(employee_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "선택한 직원을 찾을 수 없습니다")
    by_id = {e.id: e for e in employees}

    now = _utcnow()
    job = RpaJob(
        tax_office_id=client.tax_office_id,
        kind=RpaJobKind.CERTIFICATE_ISSUE,
        client_id=client.id,
        business_number=(client.business_number or "").strip(),
        business_name=client.business_name,
        requested_by_user_id=user.id,
        status=RpaJobStatus.RUNNING,
        claimed_at=now,
    )
    db.add(job)
    await db.flush()

    storage = get_storage()
    progress: dict[str, str] = {}
    failures: list[str] = []
    for employee_id in employee_ids:
        emp = by_id[employee_id]
        rrn = decrypt_rrn(emp.rrn_encrypted) if emp.rrn_encrypted else ""
        for code in codes:
            title = f"{CATALOG_BY_CODE[code]['title']} · {emp.name}"
            issue = CertificateIssue(
                tax_office_id=client.tax_office_id,
                client_id=client.id,
                requested_by_user_id=user.id,
                rpa_job_id=job.id,
                employee_id=emp.id,
                cert_type=code,
                title=title,
                options={"purpose": payload.purpose} if payload.purpose else None,
                business_number=job.business_number or None,
                business_name=client.business_name,
            )
            db.add(issue)
            key = f"{code}:{emp.id}"
            try:
                pdf = render_pdf(
                    CertificateInput(
                        kind=code,
                        employee_name=emp.name,
                        rrn_masked=mask_rrn(rrn[:6] + "-" + rrn[6:] if rrn and "-" not in rrn else rrn),
                        department=emp.department,
                        position=emp.position,
                        job_type=emp.job_type,
                        hired_at=emp.hired_at,
                        resigned_at=emp.resigned_at,
                        company_name=client.business_name,
                        business_number=client.business_number,
                        representative=client.representative,
                        purpose=payload.purpose,
                        issued_on=now.astimezone().date(),
                    )
                )
            except CertificateDataError as exc:
                issue.status = CertificateStatus.FAILED
                issue.failure_reason = str(exc)
                progress[key] = "failed"
                failures.append(f"{title}: {exc}")
                continue
            file_key = storage.make_key("certificates", ".pdf")
            storage.put_object(file_key, pdf, "application/pdf")
            issue.status = CertificateStatus.ISSUED
            issue.issued_at = now
            issue.file_key = file_key
            issue.file_name = f"{CATALOG_BY_CODE[code]['title']}_{emp.name}.pdf"
            issue.expires_at = now + RETENTION
            progress[key] = "done"

    job.step_progress = progress
    _finish(
        job,
        RpaJobStatus.FAILED if failures else RpaJobStatus.SUCCEEDED,
        "; ".join(failures) if failures else f"{len(progress)}건 발급 완료",
        now,
    )
    await db.commit()
    return await _job_out(db, job)


@router.get("/jobs/{job_id}", response_model=CertificateJobOut)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CertificateJobOut:
    return await _job_out(db, await _user_job(db, user, job_id))


@router.get("/issues/{issue_id}/file")
async def download_issue_file(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    issue = await db.get(CertificateIssue, issue_id)
    if issue is None or issue.tax_office_id != _office_id(user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "증명원을 찾을 수 없습니다")
    return await _file_response(db, issue)


async def _file_response(db: AsyncSession, issue: CertificateIssue) -> Response:
    await _purge_expired(db, [issue])
    if not issue.file_key:
        raise HTTPException(status.HTTP_410_GONE, "보관기간(30일)이 지나 서버 사본이 삭제되었습니다")
    body = get_storage().get_object(issue.file_key)
    name = issue.file_name or "certificate.pdf"
    return Response(
        content=body,
        media_type="application/pdf" if name.endswith(".pdf") else "application/octet-stream",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{_quote(name)}"},
    )


def _quote(name: str) -> str:
    from urllib.parse import quote

    return quote(name)


@router.post("/jobs/{job_id}/open-folder", response_model=CertificateJobOut)
async def request_open_folder(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CertificateJobOut:
    """[폴더 열어 확인] — 에이전트가 다음 폴링 때 자기 PC 에서 탐색기를 연다."""
    job = await _user_job(db, user, job_id)
    issues = [i for i in await _job_issues(db, job.id) if i.status == CertificateStatus.ISSUED]
    if not issues:
        raise HTTPException(status.HTTP_409_CONFLICT, "발급 완료된 증명원이 없습니다")
    now = _utcnow()
    for issue in issues:
        issue.folder_open_requested_at = now
        issue.folder_opened_at = None
    await db.commit()
    return await _job_out(db, job)


@router.post("/jobs/{job_id}/deliver", response_model=DeliverOut)
async def deliver(
    job_id: str,
    payload: DeliverIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeliverOut:
    job = await _user_job(db, user, job_id)
    issues = [i for i in await _job_issues(db, job.id) if i.status == CertificateStatus.ISSUED]
    await _purge_expired(db, issues)
    issues = [i for i in issues if i.file_key]
    if not issues:
        raise HTTPException(status.HTTP_409_CONFLICT, "발송할 증명원이 없습니다 (미발급 또는 보관기간 만료)")
    if any(i.folder_open_requested_at is None for i in issues):
        raise HTTPException(status.HTTP_409_CONFLICT, "먼저 [폴더 열어 확인]으로 발급본을 확인하세요")

    client = await db.get(Client, job.client_id)
    phone = (payload.phone or (client.contact_phone if client else None) or "").strip()
    if not phone:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "받는 사람 휴대폰 번호가 없습니다")
    office = await db.get(TaxOffice, job.tax_office_id)

    base = get_settings().app_base_url.rstrip("/")
    for issue in issues:
        issue.download_token = issue.download_token or secrets.token_urlsafe(24)
    body = delivery_body(
        office.name if office else "세무사무소",
        job.business_name,
        [(i.title, f"{base}/api/v1/public/certificates/{i.download_token}") for i in issues],
        min(_as_utc(i.expires_at) for i in issues if i.expires_at),
    )
    recipient = MessageRecipient(name=job.business_name, phone=phone)
    if payload.channel == "sms":
        result = await get_sms_channel().send(recipient, body=body)
    else:
        result = await get_alimtalk_channel().send(recipient, body=body, template_code=ALIMTALK_TEMPLATE)

    record = {
        "channel": payload.channel,
        "to": phone,
        "at": _utcnow().isoformat(),
        "accepted": result.accepted,
        "by": user.id,
    }
    for issue in issues:
        issue.deliveries = [*(issue.deliveries or []), record]
    if result.accepted:  # 하단 작업바: '고객발송 완료'로 다시 올린다
        job.step_progress = {**(job.step_progress or {}), "delivered": "done"}
        job.acknowledged_at = None
    await db.commit()
    return DeliverOut(accepted=result.accepted, channel=payload.channel, to=phone, body=body, error=result.error)


# --- 에이전트 (X-Agent-Token) ---------------------------------------------


async def _agent_job(db: AsyncSession, agent: RpaAgent, job_id: str) -> RpaJob:
    job = await db.get(RpaJob, job_id)
    if not job or job.tax_office_id != agent.tax_office_id or job.kind != RpaJobKind.CERTIFICATE_ISSUE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작업을 찾을 수 없습니다")
    if job.status != RpaJobStatus.RUNNING or job.agent_id != agent.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "이 에이전트가 진행 중인 작업이 아닙니다")
    return job


async def _agent_issue(db: AsyncSession, agent: RpaAgent, issue_id: str) -> tuple[CertificateIssue, RpaJob]:
    issue = await db.get(CertificateIssue, issue_id)
    if issue is None or issue.tax_office_id != agent.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "증명원을 찾을 수 없습니다")
    return issue, await _agent_job(db, agent, issue.rpa_job_id)


@router.post("/agent/claim", response_model=AgentClaimOut)
async def agent_claim(
    db: AsyncSession = Depends(get_db),
    agent: RpaAgent = Depends(get_current_agent),
) -> AgentClaimOut:
    """증명원 작업을 한 건 가져간다. 홈택스 세션 하나로 돌므로 사무소당 한 건씩."""
    now = _utcnow()
    agent.last_seen_at = now
    running = (
        await db.execute(
            select(RpaJob).where(
                RpaJob.tax_office_id == agent.tax_office_id,
                RpaJob.status == RpaJobStatus.RUNNING,
                RpaJob.kind == RpaJobKind.CERTIFICATE_ISSUE,
            )
        )
    ).scalars().all()
    for job in running:
        stale = job.agent_id == agent.id or (job.claimed_at and now - _as_utc(job.claimed_at) > RUNNING_TIMEOUT)
        if not stale:
            await db.commit()
            return AgentClaimOut(job=None)
        _finish(job, RpaJobStatus.FAILED, "에이전트가 발급 도중 중단됨 — 홈택스 발급 이력을 확인하세요", now)
        for issue in await _job_issues(db, job.id):
            if issue.status in (CertificateStatus.REQUESTED, CertificateStatus.RUNNING):
                issue.status = CertificateStatus.FAILED
                issue.failure_reason = "에이전트 중단"

    job = (
        await db.execute(
            select(RpaJob)
            .where(
                RpaJob.tax_office_id == agent.tax_office_id,
                RpaJob.status == RpaJobStatus.PENDING,
                RpaJob.kind == RpaJobKind.CERTIFICATE_ISSUE,
            )
            .order_by(RpaJob.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if job is None:
        await db.commit()
        return AgentClaimOut(job=None)
    job.status = RpaJobStatus.RUNNING
    job.agent_id = agent.id
    job.claimed_at = now
    issues = await _job_issues(db, job.id)
    for issue in issues:
        issue.status = CertificateStatus.RUNNING
    await db.commit()
    await db.refresh(job)
    return AgentClaimOut(job=RpaJobOut.model_validate(job), issues=[CertificateIssueOut.of(i) for i in issues])


@router.post("/agent/issues/{issue_id}/file", response_model=CertificateIssueOut)
async def agent_upload_file(
    issue_id: str,
    file: UploadFile = File(...),
    local_path: str = Form(..., max_length=500),
    db: AsyncSession = Depends(get_db),
    agent: RpaAgent = Depends(get_current_agent),
) -> CertificateIssueOut:
    issue, job = await _agent_issue(db, agent, issue_id)
    body = await file.read()
    if not body:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "빈 파일입니다")
    name = file.filename or f"{issue.title}.pdf"
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    storage = get_storage()
    key = storage.make_key("certificates", ext)
    storage.put_object(key, body, file.content_type)

    now = _utcnow()
    issue.status = CertificateStatus.ISSUED
    issue.issued_at = now
    issue.file_key = key
    issue.file_name = name
    issue.local_path = local_path
    issue.expires_at = now + RETENTION
    job.step_progress = {**(job.step_progress or {}), issue.cert_type: "done"}
    agent.last_seen_at = now
    await db.commit()
    await db.refresh(issue)
    return CertificateIssueOut.of(issue)


@router.post("/agent/issues/{issue_id}/fail", response_model=CertificateIssueOut)
async def agent_fail_issue(
    issue_id: str,
    payload: FailIn,
    db: AsyncSession = Depends(get_db),
    agent: RpaAgent = Depends(get_current_agent),
) -> CertificateIssueOut:
    issue, job = await _agent_issue(db, agent, issue_id)
    issue.status = CertificateStatus.FAILED
    issue.failure_reason = payload.reason
    job.step_progress = {**(job.step_progress or {}), issue.cert_type: "failed"}
    await db.commit()
    await db.refresh(issue)
    return CertificateIssueOut.of(issue)


@router.post("/agent/jobs/{job_id}/finish", response_model=RpaJobOut)
async def agent_finish(
    job_id: str,
    payload: FinishIn,
    db: AsyncSession = Depends(get_db),
    agent: RpaAgent = Depends(get_current_agent),
) -> RpaJob:
    job = await _agent_job(db, agent, job_id)
    issues = await _job_issues(db, job.id)
    # 개별 결과를 회신하지 않은 채 끝낸 증명원은 실패로 닫는다
    for issue in issues:
        if issue.status == CertificateStatus.RUNNING:
            issue.status = CertificateStatus.FAILED
            issue.failure_reason = issue.failure_reason or "결과 미회신"
    ok = payload.status == "SUCCEEDED" and all(i.status == CertificateStatus.ISSUED for i in issues)
    _finish(job, RpaJobStatus.SUCCEEDED if ok else RpaJobStatus.FAILED, payload.message, _utcnow())
    await db.commit()
    await db.refresh(job)
    return job


@router.get("/agent/folder-requests", response_model=list[CertificateIssueOut])
async def agent_folder_requests(
    db: AsyncSession = Depends(get_db),
    agent: RpaAgent = Depends(get_current_agent),
) -> list[CertificateIssueOut]:
    rows = await db.execute(
        select(CertificateIssue).where(
            CertificateIssue.tax_office_id == agent.tax_office_id,
            CertificateIssue.folder_open_requested_at.is_not(None),
            CertificateIssue.folder_opened_at.is_(None),
        )
    )
    return [CertificateIssueOut.of(i) for i in rows.scalars().all()]


@router.get("/agent/issues/{issue_id}/file")
async def agent_download_file(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
    agent: RpaAgent = Depends(get_current_agent),
) -> Response:
    issue = await db.get(CertificateIssue, issue_id)
    if issue is None or issue.tax_office_id != agent.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "증명원을 찾을 수 없습니다")
    return await _file_response(db, issue)


@router.post("/agent/issues/{issue_id}/folder-opened", response_model=CertificateIssueOut)
async def agent_folder_opened(
    issue_id: str,
    payload: FolderOpenedIn | None = None,
    db: AsyncSession = Depends(get_db),
    agent: RpaAgent = Depends(get_current_agent),
) -> CertificateIssueOut:
    issue = await db.get(CertificateIssue, issue_id)
    if issue is None or issue.tax_office_id != agent.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "증명원을 찾을 수 없습니다")
    if payload and payload.local_path and not issue.local_path:
        issue.local_path = payload.local_path
    issue.folder_opened_at = _utcnow()
    await db.commit()
    await db.refresh(issue)
    return CertificateIssueOut.of(issue)


# --- 공개 (고객 다운로드 링크) ----------------------------------------------


@public_router.get("/certificates/{token}")
async def public_download(token: str, db: AsyncSession = Depends(get_db)) -> Response:
    issue = (
        await db.execute(select(CertificateIssue).where(CertificateIssue.download_token == token))
    ).scalar_one_or_none()
    if issue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "링크가 만료되었거나 올바르지 않습니다")
    return await _file_response(db, issue)
