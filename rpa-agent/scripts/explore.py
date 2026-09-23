"""화면 탐색 — CDP로 붙은 에이전트 크롬의 열린 탭을 캡처하고 팝업(모달) 구조를 뽑는다.

셀렉터 실측용 (`plan/16-wehago-rpa.md` §8-1 스플래시 정리 · §9 PoC). 화면을 조작하지 않는다 — 읽기만 한다.

실행 (먼저 scripts/start-chrome.ps1 로 크롬을 띄우고 위하고에 로그인해 둔다):
    uv run python scripts/explore.py                 # 열린 탭 전부 캡처
    uv run python scripts/explore.py --goto URL      # 첫 탭을 URL로 이동 후 캡처
    uv run python scripts/explore.py --watch 60      # 60초 동안 2초마다 새 팝업이 뜨면 캡처

결과: %USERPROFILE%\\.easyone-agent\\explore\\<시각>\\
    tab<N>.png        전체 화면 (비밀번호 입력칸 가림)
    tab<N>.json       URL·제목·감지된 팝업(제목 문구·버튼·class·HTML 일부)·iframe 목록
사업자번호·이름 등이 찍힐 수 있으므로 저장소에 올리지 않는다 (PC에만 보관).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_ROOT = Path.home() / ".easyone-agent" / "explore"

# 화면을 덮는 레이어 후보: role=dialog 이거나, fixed/absolute + z-index 높음 + 일정 크기 이상.
# 입력값(value)은 HTML에서 지운다 — 비밀번호·주민번호가 파일에 남지 않게.
_FIND_OVERLAYS_JS = r"""
() => {
  // 레이어는 일정 크기 이상만, 버튼은 작아도 (닫기 X 아이콘은 24px) 잡는다
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
  // 바깥 레이어만 남긴다
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
    const checks = [...el.querySelectorAll('input[type=checkbox],label')]
      .map(c => (c.innerText || c.getAttribute('aria-label') || c.id || '').trim().slice(0, 60))
      .filter(Boolean);
    return {
      selector: selectorOf(el),
      role: el.getAttribute('role'),
      z_index: s.zIndex, position: s.position,
      rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
      text: (el.innerText || '').trim().slice(0, 800),
      buttons: buttons.slice(0, 30),
      checkboxes_labels: checks.slice(0, 20),
      html: clone.outerHTML.slice(0, 15000),
    };
  });
}
"""


def capture_page(page, out_dir: Path, name: str) -> dict:
    page.wait_for_load_state("domcontentloaded")
    shot = out_dir / f"{name}.png"
    page.screenshot(path=str(shot), mask=[page.locator("input[type=password]")])
    info = {
        "url": page.url,
        "title": page.title(),
        "overlays": [],
        "frames": [],
    }
    for frame in page.frames:
        try:
            overlays = frame.evaluate(_FIND_OVERLAYS_JS)
        except Exception as e:  # 교차 출처 iframe 등
            overlays = [{"error": str(e)[:200]}]
        if frame == page.main_frame:
            info["overlays"] = overlays
        else:
            info["frames"].append({"url": frame.url, "name": frame.name, "overlays": overlays})
    (out_dir / f"{name}.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return info


def summarize(name: str, info: dict) -> None:
    print(f"\n[{name}] {info['title']} — {info['url']}")
    groups = [("", info["overlays"])] + [(f"  (iframe {f['url'][:60]})", f["overlays"]) for f in info["frames"]]
    for label, overlays in groups:
        for o in overlays:
            if "error" in o:
                continue
            first_line = o["text"].splitlines()[0] if o["text"] else ""
            print(f"  팝업후보{label}: {o['selector'][:90]}  z={o['z_index']}  '{first_line[:50]}'")
            if o["buttons"]:
                print("     버튼:", " | ".join(b["text"] for b in o["buttons"][:10]))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)  # 백그라운드 실행 시 즉시 출력
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", default="http://127.0.0.1:9222")
    ap.add_argument("--goto", help="첫 탭을 이 URL로 이동한 뒤 캡처")
    ap.add_argument("--watch", type=int, default=0, help="N초 동안 새 팝업이 뜰 때마다 캡처")
    args = ap.parse_args()

    out_dir = OUT_ROOT / datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp)
        context = browser.contexts[0]
        pages = context.pages or [context.new_page()]
        if args.goto:
            pages[0].goto(args.goto)
            pages[0].wait_for_timeout(3000)  # SPA 렌더·안내 팝업이 뜰 시간

        for i, page in enumerate(context.pages):
            summarize(f"tab{i}", capture_page(page, out_dir, f"tab{i}"))

        if args.watch:
            seen = set()
            deadline = time.time() + args.watch
            n = 0
            while time.time() < deadline:
                for i, page in enumerate(context.pages):
                    try:
                        overlays = page.evaluate(_FIND_OVERLAYS_JS)
                    except Exception:
                        continue
                    key = tuple((o["selector"], o["text"][:100]) for o in overlays)
                    if overlays and key not in seen:
                        seen.add(key)
                        n += 1
                        summarize(f"watch{n}-tab{i}", capture_page(page, out_dir, f"watch{n}-tab{i}"))
                time.sleep(2)

        browser.close()  # CDP 연결만 끊는다 (크롬은 그대로)
    print(f"\n저장: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
