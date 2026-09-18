"""사용자 API — /api/user. plan/17 §3-9-4."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from certificate_server import storage
from certificate_server.auth import get_db
from certificate_server.models import IssueRequest, IssueStatus, Job, JobStatus
from certificate_server.schemas import IssueRequestCreate, IssueRequestOut

router = APIRouter(prefix="/api/user", tags=["user"])


@router.post("/issue-requests", response_model=IssueRequestOut, status_code=202)
def create_issue_request(
    payload: IssueRequestCreate, db: Session = Depends(get_db)
) -> IssueRequestOut:
    req = IssueRequest(
        cert_type=payload.cert_type,
        business_number=payload.business_number,
        options=payload.options,
    )
    db.add(req)
    db.flush()
    job = Job(issue_request_id=req.id, status=JobStatus.PENDING)
    db.add(job)
    db.commit()
    db.refresh(req)
    return IssueRequestOut.model_validate(req)


@router.get("/issue-requests", response_model=list[IssueRequestOut])
def list_issue_requests(db: Session = Depends(get_db)) -> list[IssueRequestOut]:
    rows = db.scalars(select(IssueRequest).order_by(IssueRequest.requested_at.desc())).all()
    return [IssueRequestOut.model_validate(r) for r in rows]


@router.get("/issue-requests/{req_id}", response_model=IssueRequestOut)
def get_issue_request(req_id: str, db: Session = Depends(get_db)) -> IssueRequestOut:
    req = db.get(IssueRequest, req_id)
    if not req:
        raise HTTPException(404, "not found")
    return IssueRequestOut.model_validate(req)


@router.get("/issue-requests/{req_id}/download")
def download(req_id: str, db: Session = Depends(get_db)) -> FileResponse:
    req = db.get(IssueRequest, req_id)
    if not req or req.status != IssueStatus.ISSUED or not req.result_file:
        raise HTTPException(404, "no file")
    path = storage.path_of(req.result_file.filename)
    return FileResponse(path, media_type=req.result_file.mime, filename=path.name)
