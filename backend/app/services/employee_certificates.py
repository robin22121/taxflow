"""직원용 증명서 PDF — 재직증명서·경력증명서 (plan/17 §4-9).

홈택스를 거치지 않고 이지원천 직원 마스터(성명·주민번호·부서·직위·입사/퇴사일)와
거래처(상호·사업자번호·대표자)로 서버가 바로 만든다. 운영 서버에 한글 폰트가 없어
나눔고딕(OFL, app/assets/fonts)을 저장소에 두고 Pillow 로 A4 한 장을 그려 PDF 로 저장한다.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
DPI = 200
PAGE = (1654, 2339)  # A4 @ 200dpi
MARGIN = 170


class CertificateDataError(ValueError):
    """증명서를 만들 수 없는 직원 데이터 (예: 퇴사자의 재직증명서, 입사일 없음)."""


@dataclass
class CertificateInput:
    kind: str  # EMPLOYMENT_CERT | CAREER_CERT
    employee_name: str
    rrn_masked: str  # 900101-1****** (뒤 6자리는 항상 가림)
    department: str | None
    position: str | None
    job_type: str | None
    hired_at: date | None
    resigned_at: date | None
    company_name: str
    business_number: str | None
    representative: str | None
    purpose: str | None
    issued_on: date


TITLES = {"EMPLOYMENT_CERT": "재 직 증 명 서", "CAREER_CERT": "경 력 증 명 서"}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "NanumGothic-Bold.ttf" if bold else "NanumGothic-Regular.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size)


def _ymd(d: date) -> str:
    return f"{d.year}년 {d.month:02d}월 {d.day:02d}일"


def validate(data: CertificateInput) -> None:
    if data.hired_at is None:
        raise CertificateDataError("입사일이 등록되지 않아 발급할 수 없습니다")
    if data.kind == "EMPLOYMENT_CERT" and data.resigned_at is not None:
        raise CertificateDataError("퇴사한 직원은 재직증명서 대신 경력증명서를 발급하세요")


def render_pdf(data: CertificateInput) -> bytes:
    validate(data)
    img = Image.new("RGB", PAGE, "white")
    draw = ImageDraw.Draw(img)
    width = PAGE[0]

    # 제목
    title_font = _font(78, bold=True)
    title = TITLES[data.kind]
    tw = draw.textlength(title, font=title_font)
    draw.text(((width - tw) / 2, 260), title, font=title_font, fill="black")

    # 표
    end = data.resigned_at
    period = f"{_ymd(data.hired_at)} ~ {_ymd(end) if end else '현재'}"  # type: ignore[arg-type]
    rows: list[tuple[str, str, str]] = [
        ("인적사항", "성    명", data.employee_name),
        ("", "주민등록번호", data.rrn_masked),
        ("근무처", "회 사 명", data.company_name),
        ("", "사업자등록번호", data.business_number or ""),
        ("", "대 표 자", data.representative or ""),
        ("근무내용", "부    서", data.department or ""),
        ("", "직    위", data.position or ""),
    ]
    if data.kind == "CAREER_CERT":
        rows.append(("", "담당업무", data.job_type or ""))
    rows.append(("", "재직기간" if data.kind == "EMPLOYMENT_CERT" else "근무기간", period))
    rows.append(("용    도", "", data.purpose or "제출용"))

    label_font = _font(34, bold=True)
    value_font = _font(36)
    top = 480
    row_h = 104
    x0, x1, x2, x3 = MARGIN, MARGIN + 230, MARGIN + 560, width - MARGIN
    for i, (group, label, value) in enumerate(rows):
        y = top + i * row_h
        draw.rectangle([x1, y, x3, y + row_h], outline="black", width=2)
        if label:
            draw.rectangle([x1, y, x2, y + row_h], outline="black", fill="#f2f2f2", width=2)
            draw.text((x1 + 30, y + 32), label, font=label_font, fill="black")
            draw.text((x2 + 30, y + 30), value, font=value_font, fill="black")
        else:  # 용도 — 라벨 칸 없이 값만
            draw.rectangle([x1, y, x3, y + row_h], outline="black", width=2)
            draw.text((x1 + 30, y + 30), value, font=value_font, fill="black")
    # 그룹 칸 (세로 병합)
    groups: list[tuple[str, int, int]] = []
    for i, (group, _, _) in enumerate(rows):
        if group:
            groups.append((group, i, i))
        else:
            name, start, _ = groups[-1]
            groups[-1] = (name, start, i)
    for name, start, stop in groups:
        y_top, y_bot = top + start * row_h, top + (stop + 1) * row_h
        draw.rectangle([x0, y_top, x1, y_bot], outline="black", fill="#f2f2f2", width=2)
        gw = draw.textlength(name, font=label_font)
        draw.text((x0 + (x1 - x0 - gw) / 2, (y_top + y_bot) / 2 - 20), name, font=label_font, fill="black")
    table_bottom = top + len(rows) * row_h

    # 증명 문구 · 발급일 · 발급자
    body_font = _font(42)
    statement = (
        "위와 같이 재직하고 있음을 증명합니다." if data.kind == "EMPLOYMENT_CERT"
        else "위와 같이 근무하였음을 증명합니다."
    )
    sw = draw.textlength(statement, font=body_font)
    draw.text(((width - sw) / 2, table_bottom + 170), statement, font=body_font, fill="black")
    issued = _ymd(data.issued_on)
    iw = draw.textlength(issued, font=body_font)
    draw.text(((width - iw) / 2, table_bottom + 330), issued, font=body_font, fill="black")

    sign_font = _font(44, bold=True)
    company = data.company_name
    rep = f"대표자  {data.representative or ''}   (인)"
    y_sign = table_bottom + 520
    for j, line in enumerate((company, rep)):
        lw = draw.textlength(line, font=sign_font)
        draw.text((x3 - lw, y_sign + j * 90), line, font=sign_font, fill="black")

    buf = io.BytesIO()
    img.save(buf, format="PDF", resolution=DPI)
    return buf.getvalue()
