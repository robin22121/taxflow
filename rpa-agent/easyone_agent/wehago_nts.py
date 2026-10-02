"""위하고 로컬 프로그램(WehagoNTS)이 띄우는 Windows 창 조작.

전자신고 파일 제작(SWER0101 [전자신고 파일 제작(Enter)]) 끝에 뜨는 "폴더 선택" 창은 크롬
화면이 아니라 `C:\\Douzone\\Wehago\\WehagoNTS`의 WinForms 창이라 Playwright로는 누를 수 없다
(2026-10-02 실측, UI Automation으로 확인):

    [Window] '폴더 선택'
      [STATIC]      'C:\\Douzone\\Wehago\\ErsData'   ← 지금 선택된 저장 폴더
      [BUTTON]      '취소'
      [BUTTON]      '확인'
      [SysTreeView32]                                  ← 폴더 트리 (경로 입력칸은 없음)

WinForms 컨트롤도 Win32 창이라 추가 패키지 없이 Win32 API(ctypes)로 찾고 누른다.
Windows가 아니면 아무 창도 찾지 않는다.
"""

from __future__ import annotations

import sys

FOLDER_DIALOG_TITLE = "폴더 선택"
_WINFORMS_PREFIX = "WindowsForms10."
_WM_GETTEXT = 0x000D
_WM_GETTEXTLENGTH = 0x000E
_BM_CLICK = 0x00F5


def _user32():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    return user32


def _enum(parent: int | None) -> list[int]:
    """parent가 None이면 최상위 창, 아니면 그 창의 모든 자식 창 핸들."""
    import ctypes
    from ctypes import wintypes

    user32 = _user32()
    found: list[int] = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(
        lambda hwnd, _: found.append(hwnd) or True
    )
    if parent is None:
        user32.EnumWindows(proc, 0)
    else:
        user32.EnumChildWindows(parent, proc, 0)
    return found


def _class(hwnd: int) -> str:
    import ctypes

    buf = ctypes.create_unicode_buffer(256)
    _user32().GetClassNameW(hwnd, buf, 256)
    return buf.value


def _text(hwnd: int) -> str:
    # 다른 프로세스의 컨트롤은 GetWindowText로 글자를 못 읽는다 — WM_GETTEXT를 보낸다.
    import ctypes

    user32 = _user32()
    length = user32.SendMessageW(hwnd, _WM_GETTEXTLENGTH, 0, 0)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.SendMessageW(hwnd, _WM_GETTEXT, length + 1, ctypes.addressof(buf))
    return buf.value


def find_folder_dialog() -> int | None:
    """보이는 위하고 "폴더 선택" 창 핸들. 없으면 None."""
    if sys.platform != "win32":
        return None
    user32 = _user32()
    for hwnd in _enum(None):
        if (
            user32.IsWindowVisible(hwnd)
            and _class(hwnd).startswith(_WINFORMS_PREFIX)
            and _text(hwnd) == FOLDER_DIALOG_TITLE
        ):
            return hwnd
    return None


def folder_dialog_path(hwnd: int) -> str:
    """창에 표시된 선택 폴더 경로 (STATIC 컨트롤 글자). 못 찾으면 빈 문자열."""
    for child in _enum(hwnd):
        if ".STATIC." in _class(child):
            text = _text(child).strip()
            if text[1:3] == ":\\":
                return text
    return ""


def answer_overwrite_prompt() -> bool:
    """"이미 기록된 파일이 있습니다. 덮어쓰시겠습니까?" 질의 창이 떠 있으면 [예(Y)]를 누른다.

    폴더 선택 [확인] 뒤, 같은 이름 파일이 있으면 뜨는 Windows 기본 메시지 창(`#32770`,
    제목 "질의")이다 (2026-10-02 실측). 파일명이 "제작일자+고정코드.01"이라 같은 날 다시
    만들면 늘 뜬다 — 제작마다 바로 withfile로 복사해 두므로 덮어써도 된다.

    Returns:
        창을 찾아 [예(Y)]를 눌렀으면 True.
    """
    if sys.platform != "win32":
        return False
    user32 = _user32()
    for hwnd in _enum(None):
        if not (user32.IsWindowVisible(hwnd) and _class(hwnd) == "#32770" and _text(hwnd) == "질의"):
            continue
        children = _enum(hwnd)
        if not any("덮어쓰" in _text(c) for c in children):
            continue  # 다른 질의 창은 건드리지 않는다
        for child in children:
            if _class(child) == "Button" and _text(child).startswith("예"):
                user32.PostMessageW(child, _BM_CLICK, 0, 0)
                return True
    return False


def confirm_folder_dialog(hwnd: int) -> None:
    """[확인] 버튼을 누른다 — 창이 닫힐 때까지 기다리지 않게 PostMessage로 보낸다."""
    for child in _enum(hwnd):
        if ".BUTTON." in _class(child) and _text(child) == "확인":
            _user32().PostMessageW(child, _BM_CLICK, 0, 0)
            return
    raise RuntimeError("위하고 '폴더 선택' 창에서 [확인] 버튼을 찾지 못했습니다")
