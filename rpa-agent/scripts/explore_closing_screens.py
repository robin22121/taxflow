"""위하고 마감·제작 5개 화면 실측 스크립트 (plan/16 §4-4 표 ⑨~⑩).

`_open_smarta_menu` 패턴을 재사용해 담당 수임처 → [급여] → SmartA → 지정 메뉴로
순차 진입하며 각 화면의 DOM/버튼/팝업을 캡처한다.

**안전 원칙**: [마감], [제작(F4)], [제작(F3)], [파일생성], [저장], [삭제] 등
어떠한 확정성 버튼도 클릭하지 않는다. 화면 로드 후 초기 상태만 캡처한다.
`--inquiry` 옵션으로 [조회] 버튼을 클릭할 수 있지만 [조회]가 데이터 조회일 뿐
아니라 실제 계산·저장을 트리거하는 경우가 있어 기본값은 False.

실행 (먼저 scripts/start-chrome.ps1 로 크롬 띄우고 위하고에 로그인 + 담당 수임처 접근 상태):
    uv run python scripts/explore_closing_screens.py --business 1234567890
    uv run python scripts/explore_closing_screens.py --business 1234567890 --inquiry
    uv run python scripts/explore_closing_screens.py --business 1234567890 --screens wht-return,local-tax-payment

결과: %USERPROFILE%\\.easyone-agent\\explore\\<시각>-closing\\ (macOS: ~/.easyone-agent/explore/<시각>-closing/)
    01-wht-return.png / .json
    02-business-income-report.png / .json
    ...
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

OUT_ROOT = Path.home() / ".easyone-agent" / "explore"

WEHAGO_URL = "https://www.wehago.com"
SIDEBAR_WAIT_MS = 30_000
UPLOAD_WAIT_MS = 30_000

# plan/16 §4-4 표 ⑨~⑩ — 위하고 T 마감·제작 5개 화면.
# (라벨, SmartA 메뉴 ID, 화면명, 캡처 후 확인할 버튼 라벨 후보)
_CLOSING_SCREENS: list[tuple[str, str, str, list[str]]] = [
    ("wht-return", "SWTA0101", "원천징수이행상황신고서",
     ["조회", "마감", "저장", "인쇄", "닫기"]),
    ("business-income-report", "SWHM0103", "거주자사업소득간이지급명세서",
     ["조회", "마감", "저장", "인쇄", "닫기"]),
    ("wht-efile", "SWER0101", "원천징수 전자신고",
     ["조회", "제작", "제작(F4)", "코드도움", "닫기"]),
    ("local-tax-payment", "SWTA0112", "지방소득세특별징수납부서",
     ["조회", "마감", "마감(F3)", "저장", "닫기"]),
    ("local-tax-efile", "SWER0109", "지방소득세특별징수전자신고",
     ["조회", "제작", "제작(F4)", "닫기"]),
]

# explore.py의 팝업 감지 JS 재사용 (input value 마스킹 포함).
_FIND_OVERLAYS_JS = r"""
() => {
  const visible = (el, minW = 80, minH = 40) => {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && +s.opacity > 0
      && r.width > minW && r.height > minH;
  };
  const cands = [];
  for (const el of document.querySelectorAll('body *')) {
    const s = getComputedStyle(el);
    const z = parseInt(s.zIndex) || 0;
    const isDialog = el.matches('[role=dialog],[role=alertdialog],[aria-modal=true]');
    if (!isDialog && !((s.position === 'fixed' || s.position === 'absolute') && z >= 100)) continue;
    if (!visible(el)) continue;
    cands.push(el);
  }
  const tops = cands.filter(el => !cands.some(o => o !== el && o.contains(el)));
  const selectorOf = el => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    if (typeof el.className === 'string' && el.className.trim())
      s += '.' + el.className.trim().split(/\s+/).join('.');
    return s;
  };
  return tops.map(el => {
    const clone = el.cloneNode(true);
    clone.querySelectorAll('input,textarea').forEach(i => { i.removeAttribute('value'); i.value = ''; });
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    const buttons = [...el.querySelectorAll('button,[role=button],a,input[type=button],input[type=submit]')]
      .filter(b => visible(b, 0, 0)).map(b => ({
        text: (b.innerText || b.value || b.getAttribute('aria-label') || '').trim().slice(0, 60),
        selector: selectorOf(b),
      })).filter(b => b.text);
    return {
      selector: selectorOf(el),
      role: el.getAttribute('role'),
      z_index: s.zIndex, position: s.position,
      rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
      text: (el.innerText || '').trim().slice(0, 800),
      buttons: buttons.slice(0, 30),
      html: clone.outerHTML.slice(0, 15000),
    };
  });
}
"""

# 화면 상단의 툴바 버튼(F4 마감·F3 조회 등) 목록을 통째로 뽑는다.
# SmartA 는 최상단 아이콘 툴바(button.btn_top·button.btn_toolbar·[class*=toolbar])에 신고·마감 액션이 모여 있어
# 이걸 잡아 두면 이후 자동화 코드에서 셀렉터를 특정하기 쉽다.
_TOOLBAR_JS = r"""
() => {
  const visible = (el) => {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && +s.opacity > 0
      && r.width > 4 && r.height > 4;
  };
  const selectorOf = el => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    if (typeof el.className === 'string' && el.className.trim())
      s += '.' + el.className.trim().split(/\s+/).join('.');
    return s;
  };
  // 상단(y<220)에 있는 모든 버튼 후보 — SmartA는 화면 상단에 툴바가 붙어 있음.
  const buttons = [];
  for (const el of document.querySelectorAll('button,[role=button],a.btn,input[type=button],input[type=submit]')) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.y > 220) continue;  // 상단 툴바만
    const label = (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
    if (!label) continue;
    buttons.push({
      text: label.slice(0, 40),
      selector: selectorOf(el),
      x: Math.round(r.x), y: Math.round(r.y),
      w: Math.round(r.width), h: Math.round(r.height),
      key: el.getAttribute('data-key') || el.getAttribute('data-shortcut') || '',
    });
  }
  buttons.sort((a, b) => a.x - b.x);
  return buttons;
}
"""


def _clean_business_number(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _dismiss_splash(page: Page) -> None:
    """위하고 T 로그인 후 뜨는 스플래시/2차 인증 다이얼로그 닫기 (wehago.py 참조)."""
    for _ in range(3):
        page.wait_for_timeout(400)
        dialog = page.locator("div.LUX_basic_dialog").first
        if dialog.count() == 0:
            return
        close = dialog.locator("button:has-text('닫기')")
        if close.count() == 0:
            return
        close.last.click(force=True)
        page.wait_for_timeout(400)


def _wait_for_no_dimmed(page: Page) -> None:
    """검색 결과 로딩 dimmed 오버레이 사라질 때까지 대기."""
    try:
        page.locator("div.dimmed").first.wait_for(state="hidden", timeout=5000)
    except Exception:
        pass


def open_smarta_new_tab(context, business_number: str, cdp_url: str):
    """위하고 T main → 담당 수임처 검색 → [급여] click → SmartA 새 탭 반환.

    wehago.py `_open_smarta_menu` 앞부분(메뉴 클릭 직전까지)의 재구성.
    """
    page = context.pages[0] if context.pages else context.new_page()
    for other in list(context.pages):
        if other is not page and "smarta.wehagot.com" in other.url:
            other.close()

    page.goto(f"{WEHAGO_URL}/#/main")
    _dismiss_splash(page)
    _wait_for_no_dimmed(page)
    search = page.locator("input[placeholder*='사업자등록번호']").first
    search.wait_for(state="visible", timeout=SIDEBAR_WAIT_MS)
    target = _clean_business_number(business_number)
    search.fill(target)
    search.press("Enter")

    rows = page.locator("li:has(p.company_num)")
    matching: list[int] = []
    for _ in range(20):
        page.wait_for_timeout(500)
        numbers = [_clean_business_number(t) for t in rows.locator("p.company_num").all_inner_texts()]
        matching = [i for i, n in enumerate(numbers) if n == target]
        if matching and len(numbers) == len(matching):
            break
    if len(matching) != 1:
        raise RuntimeError(
            f"담당 수임처에서 사업자번호 {business_number} 가 정확히 1건이 아닙니다 ({len(matching)}건)"
        )
    row = rows.nth(matching[0])
    name = row.locator(".company_name a").first.inner_text().strip()
    number = _clean_business_number(row.locator("p.company_num").inner_text())

    with context.expect_page(timeout=UPLOAD_WAIT_MS) as new_tab:
        row.locator("button.btn_quick", has_text=re.compile(r"^급여$")).click()
    smarta = new_tab.value
    smarta.wait_for_load_state()
    return smarta, name, number


def click_menu(smarta: Page, menu_id: str) -> None:
    """SmartA 사이드바에서 지정 메뉴 링크 클릭 (a#{menu_id}.text_link)."""
    menu = smarta.locator(f"a#{menu_id}.text_link")
    menu.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
    menu.click()
    smarta.wait_for_load_state("domcontentloaded")
    smarta.wait_for_timeout(1500)  # SPA 렌더 안정화


def capture(page: Page, out_dir: Path, name: str, expected_buttons: list[str]) -> dict:
    """스크린샷 + DOM/툴바/팝업 정보 저장."""
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(500)
    shot = out_dir / f"{name}.png"
    page.screenshot(path=str(shot), mask=[page.locator("input[type=password]")], full_page=False)

    info: dict = {
        "menu_name": name,
        "url": page.url,
        "title": page.title(),
        "toolbar_buttons": [],
        "overlays": [],
        "frames": [],
    }

    # 상단 툴바 버튼 (마감·제작·조회가 여기 있을 확률이 높음)
    try:
        info["toolbar_buttons"] = page.evaluate(_TOOLBAR_JS)
    except Exception as e:
        info["toolbar_buttons_error"] = str(e)[:200]

    # 팝업 오버레이 (변환파일 비밀번호 입력 등)
    for frame in page.frames:
        try:
            overlays = frame.evaluate(_FIND_OVERLAYS_JS)
        except Exception as e:
            overlays = [{"error": str(e)[:200]}]
        if frame == page.main_frame:
            info["overlays"] = overlays
        else:
            info["frames"].append({"url": frame.url, "name": frame.name, "overlays": overlays})

    # 기대 버튼이 실제로 툴바에 있는지 매칭 결과도 남긴다 — 자동화 코드 짤 때 유용
    matches: dict[str, list[str]] = {label: [] for label in expected_buttons}
    for b in info["toolbar_buttons"]:
        for label in expected_buttons:
            if label in b.get("text", ""):
                matches[label].append(b.get("selector", ""))
    info["expected_button_matches"] = matches

    (out_dir / f"{name}.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return info


def summarize(name: str, info: dict) -> None:
    print(f"\n[{name}] {info['title']} — {info['url']}")
    tb = info.get("toolbar_buttons") or []
    if tb:
        print(f"  상단 툴바 {len(tb)}개: " + " | ".join(b["text"] for b in tb[:12]))
    matches = info.get("expected_button_matches") or {}
    for label, selectors in matches.items():
        status = "✅" if selectors else "❌"
        head = selectors[0][:80] if selectors else "미검출"
        print(f"  {status} [{label}]  →  {head}")
    for o in info.get("overlays") or []:
        if "error" in o:
            continue
        first_line = (o.get("text") or "").splitlines()[0] if o.get("text") else ""
        print(f"  팝업: {o['selector'][:80]}  '{first_line[:50]}'")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", default="http://127.0.0.1:9222",
                    help="위하고 크롬 CDP 주소 (기본 9222 — start-chrome.ps1 -Port 9222)")
    ap.add_argument("--business", required=True,
                    help="담당 수임처 사업자번호 (하이픈 무관, 10자리)")
    ap.add_argument("--screens",
                    help=f"쉼표로 구분한 라벨. 기본은 5개 전부. "
                         f"선택지: {','.join(s[0] for s in _CLOSING_SCREENS)}")
    ap.add_argument("--out-root", help="저장 루트 (기본 ~/.easyone-agent/explore)")
    ap.add_argument("--inquiry", action="store_true",
                    help="[조회] 버튼을 자동 클릭해 조회 후 상태도 캡처 "
                         "(주의: 화면에 따라 계산·저장을 트리거할 수 있음)")
    args = ap.parse_args()

    selected = _CLOSING_SCREENS
    if args.screens:
        wanted = {s.strip() for s in args.screens.split(",")}
        selected = [s for s in _CLOSING_SCREENS if s[0] in wanted]
        if not selected:
            print(f"에러: --screens 에 유효한 라벨이 없습니다. 선택지: {[s[0] for s in _CLOSING_SCREENS]}",
                  file=sys.stderr)
            return 2

    root = Path(args.out_root).expanduser() if args.out_root else OUT_ROOT
    out_dir = root / (datetime.now().strftime("%Y%m%dT%H%M%S") + "-closing")
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"저장 경로: {out_dir}")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp)
        context = browser.contexts[0]

        # 1. 위하고 T main → 담당 수임처 → [급여] → SmartA (1회)
        smarta, name, number = open_smarta_new_tab(context, args.business, args.cdp)
        print(f"수임처: {name} ({number}) — SmartA 탭 열림")

        # 2. 5개 메뉴 순회
        for idx, (label, menu_id, screen_name, expected) in enumerate(selected, start=1):
            slot = f"{idx:02d}-{label}"
            print(f"\n== {slot} · {menu_id} · {screen_name} ==")
            try:
                click_menu(smarta, menu_id)
            except Exception as e:
                print(f"  ❌ 메뉴 진입 실패: {e}")
                (out_dir / f"{slot}-error.json").write_text(
                    json.dumps({"menu_id": menu_id, "error": str(e)}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                continue

            info = capture(smarta, out_dir, slot, expected)
            summarize(slot, info)

            if args.inquiry:
                # [조회] 버튼이 툴바에 있으면 클릭 후 재캡처.
                inquiry_selectors = info["expected_button_matches"].get("조회", [])
                if inquiry_selectors:
                    print("  → [조회] 클릭 후 재캡처 (--inquiry)")
                    try:
                        smarta.locator(inquiry_selectors[0]).first.click()
                        smarta.wait_for_timeout(2500)
                        info2 = capture(smarta, out_dir, f"{slot}-after-inquiry", expected)
                        summarize(f"{slot}-after-inquiry", info2)
                    except Exception as e:
                        print(f"  ⚠️ [조회] 클릭 실패: {e}")

        browser.close()

    print(f"\n완료. 저장: {out_dir}")
    print("결과 파일을 검토한 뒤 wehago.py 에 셀렉터를 옮기세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
