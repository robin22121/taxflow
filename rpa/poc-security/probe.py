"""컨트롤에 텍스트 입력이 반영되는지 확인.

사용법:
    python probe.py --title "메모장" --control-key class_name --control "Edit" --text "hello"
    python probe.py --title "SmartA" --control-key auto_id --control "txt신고번호" --text "12345"
"""

import argparse
import sys
import traceback

from pywinauto import Application


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True, help="창 제목 일부")
    ap.add_argument("--control-key", default="auto_id", choices=["auto_id", "title", "class_name"])
    ap.add_argument("--control", required=True, help="컨트롤 식별자")
    ap.add_argument("--text", required=True, help="입력할 텍스트")
    ap.add_argument("--backend", default="uia", choices=["uia", "win32"])
    args = ap.parse_args()

    try:
        app = Application(backend=args.backend).connect(title_re=f".*{args.title}.*", timeout=5)
        win = app.top_window()
    except Exception as e:
        print(f"[attach] FAIL: {e}")
        return 2

    try:
        ctrl = win.child_window(**{args.control_key: args.control}).wrapper_object()
        print(f"[find] OK: {ctrl}")
    except Exception as e:
        print(f"[find] FAIL: {e}")
        return 3

    try:
        ctrl.set_text(args.text)
        print(f"[set_text] OK")
        return 0
    except Exception as e:
        print(f"[set_text] FAIL: {e} → type_keys fallback")

    try:
        ctrl.set_focus()
        ctrl.type_keys(args.text, with_spaces=True)
        print(f"[type_keys] OK")
        return 0
    except Exception as e:
        print(f"[type_keys] FAIL: {e}")
        traceback.print_exc()
        return 4


if __name__ == "__main__":
    sys.exit(main())
