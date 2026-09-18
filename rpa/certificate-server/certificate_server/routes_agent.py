"""에이전트 API — /api/agent. plan/17 §3-9-4."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from certificate_server import storage
from certificate_server.auth import get_db, require_agent
from certificate_server.models import (
    Agent,
    CertificateFile,
    IssueRequest,
    IssueStatus,
    Job,
    JobStatus,
)
from certificate_server.schemas import JobOut

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/jobs/next", response_model=JobOut | None)
def claim_next_job(
    agent: Agent = Depends(require_agent), db: Session = Depends(get_db)
) -> JobOut | None:
    """가장 오래된 PENDING 잡 하나를 CLAIMED 로 전이 후 반환."""
    agent.last_seen_at = dt.datetime.now(dt.UTC)
    job = db.scalar(
        select(Job).where(Job.status == JobStatus.PENDING).order_by(Job.created_at).limit(1)
    )
    if not job:
        db.commit()
        return None
    job.status = JobStatus.CLAIMED
    job.agent_id = agent.id
    job.claimed_at = dt.datetime.now(dt.UTC)
    req = db.get(IssueRequest, job.issue_request_id)
    req.status = IssueStatus.RUNNING
    db.commit()
    return JobOut(
        id=job.id,
        issue_request_id=req.id,
        status=job.status,
        cert_type=req.cert_type,
        business_number=req.business_number,
        options=req.options,
    )


@router.post("/jobs/{job_id}/result")
def submit_result(
    job_id: str,
    file: UploadFile = File(...),
    success: bool = Form(True),
    message: str = Form(""),
    agent: Agent = Depends(require_agent),
    db: Session = Depends(get_db),
) -> dict:
    job = db.get(Job, job_id)
    if not job or job.agent_id != agent.id:
        raise HTTPException(404, "job not found or not claimed by this agent")
    req = db.get(IssueRequest, job.issue_request_id)
    now = dt.datetime.now(dt.UTC)

    if success:
        data = file.file.read()
        ext = (
            ".pdf"
            if (file.content_type or "").endswith("pdf") or (file.filename or "").endswith(".pdf")
            else ".png"
        )
        cert_file = CertificateFile(
            filename="",  # save 후 채움
            mime=file.content_type or "application/octet-stream",
            sha256="",
        )
        db.add(cert_file)
        db.flush()
        rel, sha = storage.save(cert_file.id, ext, data)
        cert_file.filename = rel
        cert_file.sha256 = sha
        req.status = IssueStatus.ISSUED
        req.result_file_id = cert_file.id
        job.status = JobStatus.SUCCEEDED
    else:
        req.status = IssueStatus.FAILED
        req.failure_reason = message
        job.status = JobStatus.FAILED

    job.finished_at = now
    job.result_message = message
    db.commit()
    return {"ok": True, "issue_request_id": req.id, "status": req.status.value}
