"""SmartA 창에 attach → 컨트롤 트리 dump → 스크린샷 저장.

사용법:
    python attach.py --title "메모장"           # 로컬 학습용
    python attach.py --title "SmartA" --backend win32
"""

import argparse
import contextlib
import datetime
import sys
import traceback
from pathlib import Path

from pywinauto import Application


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True, help="창 제목 일부 (정규식)")
    ap.add_argument("--backend", default="uia", choices=["uia", "win32"])
    ap.add_argument("--depth", type=int, default=6, help="컨트롤 트리 dump 깊이")
    ap.add_argument("--out", default="dumps", help="결과 저장 폴더")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    print(f"[attach] backend={args.backend}, title~='{args.title}'")
    try:
        app = Application(backend=args.backend).connect(title_re=f".*{args.title}.*", timeout=5)
        win = app.top_window()
        print(f"[attach] OK: {win.window_text()!r}")
    except Exception as e:
        print(f"[attach] FAIL: {e}")
        traceback.print_exc()
        return 2

    dump = out / f"controls-{args.backend}-{stamp}.txt"
    try:
        with open(dump, "w", encoding="utf-8") as f, contextlib.redirect_stdout(f):
            win.print_control_identifiers(depth=args.depth)
        size = dump.stat().st_size
        print(f"[dump] saved: {dump} ({size:,} bytes)")
        if size < 200:
            print("[dump] ⚠️  파일이 매우 작음 — UIA 접근 차단 가능성. win32 backend로 재시도 권장")
    except Exception as e:
        print(f"[dump] FAIL: {e}")
        traceback.print_exc()

    shot = out / f"screen-{args.backend}-{stamp}.png"
    try:
        win.capture_as_image().save(shot)
        print(f"[shot] saved: {shot}")
    except Exception as e:
        print(f"[shot] FAIL (무시): {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
