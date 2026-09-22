"""CLI 진입점.

  python -m certificate_agent setup   자격증명 등록 (Windows 자격 증명 관리자)
  python -m certificate_agent run     폴링 루프 시작
  python -m certificate_agent show    저장 상태 확인 (값 마스킹)
  python -m certificate_agent clear   저장 항목 삭제

개발용 (로그인해 둔 브라우저에 부착 — 서버·keyring 불필요):
  python -m certificate_agent chrome  디버깅 포트 연 Chrome 실행 → 직접 홈택스 로그인
  python -m certificate_agent attach  그 Chrome 에 붙어 사업자등록증명 발급
  python -m certificate_agent snap    그 Chrome 의 지금 화면 HTML·PNG 저장 (셀렉터 수집)
"""

from __future__ import annotations

import platform
import subprocess
import time
from getpass import getpass
from pathlib import Path

import typer

from certificate_agent import config
from certificate_agent.issue_flow import WORK, _dump, _find_hometax_page, execute_attached
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
    agent_token = input("에이전트 토큰 (관리자 CLI 로 발급받은 값): ").strip()
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
    for k in config.KEYS:
        typer.echo(f"  {k:<22} = {_mask(config.load(k))}")


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


CDP_PORT = 9222
CHROME_PATHS = {
    "Darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
    "Windows": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
}
# Chrome 136+ 는 기본 프로필에서 원격 디버깅을 막으므로 전용 프로필을 쓴다
CHROME_PROFILE = WORK / "chrome-profile"


@app.command()
def chrome(port: int = CDP_PORT) -> None:
    """원격 디버깅 포트를 연 시스템 Chrome 을 홈택스로 띄운다. 로그인은 직접."""
    exe = next((c for c in CHROME_PATHS.get(platform.system(), []) if Path(c).exists()), None)
    if exe is None:
        typer.echo(f"[!] Chrome 을 찾지 못함: {CHROME_PATHS.get(platform.system())}")
        raise typer.Exit(1)
    CHROME_PROFILE.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={CHROME_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://www.hometax.go.kr/",
    ])
    typer.echo(f"[+] Chrome 실행 (CDP :{port}, 프로필 {CHROME_PROFILE})")
    typer.echo("[*] 브라우저에서 홈택스에 직접 로그인한 뒤 `attach` 를 실행하세요. 창은 계속 열어 두세요.")


@app.command()
def attach(
    biz: str = typer.Option(..., prompt="발급할 사업자등록번호", help="사업자등록번호 (하이픈 무관)"),
    rrn_disclosed: bool = typer.Option(False, help="주민등록번호 공개 (기본 비공개)"),
    port: int = CDP_PORT,
) -> None:
    """로그인해 둔 Chrome 에 붙어 사업자등록증명을 발급하고 work/ 에 저장."""
    job = {
        "cert_type": "BUSINESS_REGISTRATION",
        "business_number": biz,
        "options": {"rrn_disclosed": rrn_disclosed},
    }
    data, filename, _mime, msg = execute_attached(job, f"http://127.0.0.1:{port}")
    WORK.mkdir(exist_ok=True)
    out = WORK / f"{int(time.time())}_{filename}"
    out.write_bytes(data)
    typer.echo(f"[+] {msg} → {out}")


@app.command()
def snap(tag: str = "snap", port: int = CDP_PORT) -> None:
    """로그인해 둔 Chrome 의 홈택스 탭을 work/ 에 HTML·PNG 로 저장."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        page = _find_hometax_page(browser.contexts[0])
        typer.echo(f"[+] {page.url} → {_dump(page, tag)}.html/.png")


if __name__ == "__main__":
    app()
