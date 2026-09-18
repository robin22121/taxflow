"""X-Agent-Token 검증."""

from __future__ import annotations

import hashlib

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from certificate_server.db import get_session
from certificate_server.models import Agent


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def get_db() -> Session:
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def require_agent(
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
    db: Session = Depends(get_db),
) -> Agent:
    token_hash = sha256_hex(x_agent_token)
    agent = db.scalar(
        select(Agent).where(Agent.token_hash == token_hash, Agent.revoked_at.is_(None))
    )
    if not agent:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid agent token")
    return agent
