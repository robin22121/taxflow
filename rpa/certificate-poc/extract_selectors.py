"""out/*.html 에서 버튼·링크 후보만 뽑아 출력한다.

HTML 원본은 로그인 상태 페이지라 사업자번호·상호가 들어 있어 통째로 공유하기
어렵다. 이 스크립트는 클릭 대상이 될 만한 요소의 셀렉터 정보만 추려 출력하고,
숫자는 마스킹한다.

실행: uv run python extract_selectors.py
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

OUT = Path(__file__).parent / "out"

KEYWORDS = ["사업자등록증명", "신청", "발급", "출력", "즉시발급", "조회", "확인"]
# 폼 컨트롤은 키워드와 무관하게 전부 뽑는다 (사용용도·제출처·수령방법 등 select 포함)
ALWAYS = {"input", "button", "select", "option"}
# 텍스트가 키워드에 걸릴 때만 뽑는다
KEYWORD_ONLY = {"a", "span", "td", "li"}
CLICKABLE = ALWAYS | KEYWORD_ONLY
ATTRS = ("id", "class", "title", "value", "type", "href", "onclick", "name")


def mask(text: str) -> str:
    """연속 숫자 3자리 이상은 마스킹 (사업자번호·주민번호·금액).

    화면 텍스트에만 적용한다. id·href·class 는 셀렉터 자체라 가리면 쓸모가 없고,
    홈택스 WebSquare 의 요소 id 는 개인정보를 담지 않는다.
    """
    return re.sub(r"\d{3,}", lambda m: "#" * len(m.group()), text)


class Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hits: list[str] = []
        self.stack: list[tuple[str, dict, int]] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag not in CLICKABLE:
            return
        d = {k: v for k, v in attrs if k in ATTRS and v}
        self.stack.append((tag, d, len(self.hits)))
        # 폼 컨트롤은 텍스트 없이도 그 자체가 필요하므로 무조건 emit
        if tag in ALWAYS:
            self.emit(tag, d, "")
            if tag in ("input", "option"):
                self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1][0] != tag:
            return
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text or not self.stack:
            return
        tag, d, _ = self.stack[-1]
        if tag in KEYWORD_ONLY and not any(kw in text for kw in KEYWORDS):
            return
        self.emit(tag, d, text)

    def emit(self, tag: str, d: dict, text: str) -> None:
        parts = [f"<{tag}"]
        for k in ATTRS:
            if k in d:
                v = d[k]
                if k == "onclick":
                    v = v[:80]
                parts.append(f'{k}="{v}"')
        line = " ".join(parts) + ">"
        if text:
            line += f"  text={mask(text)[:60]!r}"
        if line not in self.hits:
            self.hits.append(line)


def scan(path: Path, w) -> None:
    w("=" * 70)
    w(f"# {path.name}")
    w("=" * 70)
    c = Collector()
    try:
        c.feed(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        w(f"[!] parse failed: {exc}")
        return
    if not c.hits:
        w("(추출된 요소 없음)")
    for h in c.hits:
        w("  " + h)
    w("")


def main() -> None:
    files = sorted(OUT.glob("*.html"))
    if not files:
        print(f"[!] {OUT} 에 html 이 없습니다. 먼저 issue.py 를 실행하세요.")
        return

    # PowerShell 의 > 리다이렉트는 콘솔 인코딩(cp949)을 타서 UnicodeEncodeError 가
    # 나거나 UTF-16 으로 저장된다. 스크립트가 직접 UTF-8 로 쓴다.
    dest = Path(__file__).parent / "selectors.txt"
    lines: list[str] = []
    for f in files:
        scan(f, lines.append)
    dest.write_text("\n".join(lines), encoding="utf-8")

    print(f"[+] {len(files)} 파일에서 {len(lines)} 줄 추출")
    print(f"[+] 저장 → {dest}")


if __name__ == "__main__":
    main()
