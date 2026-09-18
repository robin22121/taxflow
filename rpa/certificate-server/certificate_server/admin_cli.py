"""관리자 CLI — 에이전트 등록·토큰 발급·폐기.

실행:
  uv run python -m certificate_server.admin_cli register --name Windows-김연호
  uv run python -m certificate_server.admin_cli list
  uv run python -m certificate_server.admin_cli revoke <agent_id>
"""

from __future__ import annotations

import datetime as dt
import secrets

import typer
from sqlalchemy import select

from certificate_server.auth import sha256_hex
from certificate_server.db import get_session, init_db
from certificate_server.models import Agent

app = typer.Typer(help="Certificate server admin CLI")


@app.command()
def register(name: str = typer.Option(..., help="에이전트 이름")) -> None:
    """새 에이전트 등록. 토큰은 1회만 노출된다."""
    init_db()
    token = secrets.token_urlsafe(32)
    agent = Agent(name=name, token_hash=sha256_hex(token))
    db = get_session()
    try:
        db.add(agent)
        db.commit()
        db.refresh(agent)
    finally:
        db.close()
    typer.echo(f"id: {agent.id}")
    typer.echo(f"name: {agent.name}")
    typer.echo(f"token: {token}   ← 1회만 표시. Windows PC setup 에 넣으세요.")


@app.command("list")
def list_agents() -> None:
    init_db()
    db = get_session()
    try:
        rows = db.scalars(select(Agent)).all()
    finally:
        db.close()
    for a in rows:
        status = "revoked" if a.revoked_at else "active"
        typer.echo(f"{a.id}  {a.name:<20}  {status}  last_seen={a.last_seen_at}")


@app.command()
def revoke(agent_id: str) -> None:
    init_db()
    db = get_session()
    try:
        a = db.get(Agent, agent_id)
        if not a:
            typer.echo("not found")
            raise typer.Exit(1)
        a.revoked_at = dt.datetime.now(dt.UTC)
        db.commit()
        typer.echo(f"revoked {agent_id}")
    finally:
        db.close()


if __name__ == "__main__":
    app()
