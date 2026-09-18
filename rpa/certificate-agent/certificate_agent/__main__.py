"""CLI 진입점.

  python -m certificate_agent setup   자격증명 등록 (Windows 자격 증명 관리자)
  python -m certificate_agent run     폴링 루프 시작
  python -m certificate_agent show    저장 상태 확인 (값 마스킹)
  python -m certificate_agent clear   저장 항목 삭제
"""

from __future__ import annotations

from getpass import getpass

import typer

from certificate_agent import config
from certificate_agent.runner import run_loop

app = typer.Typer(help="Certificate agent CLI")


def _mask(v: str | None) -> str:
    if not v:
        return "(missing)"
    if len(v) <= 4:
        return "*" * len(v)
    return v[:2] + "*" * (len(v) - 4) + v[-2:]


@app.command()
def setup() -> None:
    """대화형으로 자격증명·서버 URL·에이전트 토큰 저장."""
    typer.echo("[*] 값은 Windows 자격 증명 관리자에 저장됩니다. 파일에 남지 않습니다.")
    server_url = input("서버 URL (예: http://192.168.1.10:8100): ").strip()
    agent_token = getpass("에이전트 토큰 (관리자 CLI 로 발급받은 값): ").strip()
    hometax_id = input("홈택스 아이디: ").strip()
    hometax_pw = getpass("홈택스 비밀번호: ")
    rrn_prefix = getpass("2차 인증 주민번호 앞 6자리: ").strip()
    rrn_suffix = getpass("2차 인증 주민번호 뒤 1자리: ").strip()

    config.save("server_url", server_url)
    config.save("agent_token", agent_token)
    config.save("hometax_id", hometax_id)
    config.save("hometax_pw", hometax_pw)
    config.save("hometax_rrn_prefix", rrn_prefix)
    config.save("hometax_rrn_suffix", rrn_suffix)
    typer.echo("[+] saved.")


@app.command()
def show() -> None:
    """저장된 값의 마스킹된 요약 표시."""
    for k in config.KEYS:
        v = config.load(k)
        typer.echo(f"  {k:<22} = {_mask(v)}")


@app.command()
def clear() -> None:
    """저장된 자격증명 삭제."""
    config.clear()
    typer.echo("[+] cleared.")


@app.command()
def run() -> None:
    """폴링 루프 시작."""
    cfg = config.load_all()
    if not cfg:
        typer.echo("[!] 자격증명이 없습니다. 먼저 `setup` 을 실행하세요.")
        raise typer.Exit(1)
    run_loop(cfg)


if __name__ == "__main__":
    app()
