"""Convert uploaded files into the plain-text representation our AI parser expects.

Supported types in Phase 1:
- Audio (.mp3 / .m4a / .wav / .aac) — put to Object Storage, presign URL, send to STT.
- Excel (.xlsx / .xls) — read cells with openpyxl, build a tab-separated text dump.
- CSV (.csv) — decoded as text directly.
- Image (.png / .jpg / .jpeg / .webp) — pass-through to Claude Vision via the
  ``images`` list on ``IntakeResult``.
- PDF (.pdf) — render each page to PNG via pypdfium2 and pass to Vision (max 20 pages).

RRN 사이드채널 (plan/10-privacy-security.md §2.0·G4):
- 엑셀·CSV 반입 시 결정론 파서로 ``{이름 → rrn_last4, rrn_encrypted_b64}`` 맵을 추출해
  ``IntakeResult.rrn_map`` 에 담는다. LLM 프롬프트 텍스트는 종전대로 ``redact_pii`` 로
  마스킹된 채 나가고, 원본 RRN 은 서버 내부에서만 암호화된 형태로 존재한다.
"""

from __future__ import annotations

import base64
import csv
import io
import logging
from dataclasses import dataclass, field
from typing import Iterable

from openpyxl import load_workbook

from app.services.crypto import encrypt_rrn, normalize_rrn, rrn_last4 as _rrn_last4
from app.services.pii import redact_pii
from app.services.storage import ObjectStorage
from app.services.wehago_payroll_parser import WehagoPayrollRow, parse_wehago_workbook

logger = logging.getLogger(__name__)


AUDIO_EXTS = (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac")
EXCEL_EXTS = (".xlsx", ".xlsm", ".xls")
CSV_EXTS = (".csv",)
TEXT_EXTS = (".txt",)
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
PDF_EXTS = (".pdf",)

# Vision 비용·응답 시간 보호 — 너무 큰 PDF는 잘라서 처리
_MAX_PDF_PAGES = 20
_PDF_RENDER_DPI = 150


@dataclass(slots=True)
class IntakeResult:
    text: str
    kind: str  # "audio" | "excel" | "csv" | "image" | "pdf" | "unknown"
    storage_key: str | None = None
    note: str | None = None
    # Vision 모델로 보낼 (bytes, mime) 리스트. 이미지는 1개, PDF는 페이지 수만큼.
    images: list[tuple[bytes, str]] = field(default_factory=list)
    # 위하고T 22컬럼 급여대장이 감지되면 결정론적으로 파싱된 행 리스트. LLM 우회 신호.
    structured_payroll: list[WehagoPayrollRow] | None = None
    # 반입 파일에서 결정론적으로 뽑은 {이름 → {rrn_last4, rrn_encrypted_b64}} 맵.
    # AI 파싱 결과의 이름과 매칭해 사이드채널로 병합한다 (plan/10 §G4).
    rrn_map: dict[str, dict[str, str]] = field(default_factory=dict)


def _is_audio(filename: str) -> bool:
    return filename.lower().endswith(AUDIO_EXTS)


def _is_excel(filename: str) -> bool:
    return filename.lower().endswith(EXCEL_EXTS)


def _is_csv(filename: str) -> bool:
    return filename.lower().endswith(CSV_EXTS)


def _is_text(filename: str) -> bool:
    return filename.lower().endswith(TEXT_EXTS)


def _is_image(filename: str) -> bool:
    return filename.lower().endswith(IMAGE_EXTS)


def _is_pdf(filename: str) -> bool:
    return filename.lower().endswith(PDF_EXTS)


def _pdf_to_page_images(blob: bytes) -> list[tuple[bytes, str]]:
    """Render each PDF page to PNG bytes. Returns up to _MAX_PDF_PAGES."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(blob)
    pages: list[tuple[bytes, str]] = []
    scale = _PDF_RENDER_DPI / 72  # PDF default DPI = 72
    for i in range(min(len(pdf), _MAX_PDF_PAGES)):
        page = pdf[i]
        pil_image = page.render(scale=scale).to_pil()
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        pages.append((buf.getvalue(), "image/png"))
    if len(pdf) > _MAX_PDF_PAGES:
        logger.warning(
            "[file-intake] PDF has %d pages, only processing first %d",
            len(pdf), _MAX_PDF_PAGES,
        )
    return pages


# ─── RRN 결정론 추출 (사이드채널) ────────────────────────────────────────────
# api/imports.py 의 _EMPLOYEE_ALIASES 와 정합. 저 파일이 바뀌면 함께 갱신 필요.
_NAME_HEADERS = {"성명", "이름", "직원명", "사원명", "name"}
_RRN_HEADERS = {"주민등록번호", "주민번호", "rrn", "주민"}


def _normalize_header(cell: object) -> str:
    return str(cell or "").strip().lower().replace(" ", "")


def _find_col(headers: list[str], candidates: set[str]) -> int | None:
    norm_candidates = {c.strip().lower().replace(" ", "") for c in candidates}
    for i, h in enumerate(headers):
        if _normalize_header(h) in norm_candidates:
            return i
    return None


def _entry_from_rrn(raw: str) -> dict[str, str] | None:
    """정상 형식 RRN → {rrn_last4, rrn_encrypted_b64}. 형식 오류면 ``None``."""
    try:
        digits = normalize_rrn(raw)
    except ValueError:
        return None
    ct = encrypt_rrn(digits)
    return {
        "rrn_last4": _rrn_last4(digits),
        "rrn_encrypted_b64": base64.b64encode(ct).decode("ascii"),
    }


def _extract_rrn_map_excel(blob: bytes) -> dict[str, dict[str, str]]:
    """엑셀 워크북 전체를 훑어 이름·주민번호 컬럼 쌍이 있는 시트에서 맵을 만든다.

    시트별로 헤더를 검사하며, 이름 컬럼과 RRN 컬럼이 동시에 있는 시트만 채택한다.
    잘못된 RRN(자릿수·생년월일·성별코드 오류)은 조용히 스킵 — 원본 파일은 그대로 남고
    UI 는 프리필 없이 사용자가 직접 입력하는 흐름으로 자연 폴백.
    """
    result: dict[str, dict[str, str]] = {}
    try:
        wb = load_workbook(io.BytesIO(blob), data_only=True, read_only=True)
    except Exception:  # noqa: BLE001
        logger.warning("[rrn-map] excel open failed")
        return result

    for ws in wb.worksheets:
        rows_iter = ws.iter_rows(values_only=True)
        header_row = next(rows_iter, None)
        if not header_row:
            continue
        headers = [str(c or "").strip() for c in header_row]
        name_idx = _find_col(headers, _NAME_HEADERS)
        rrn_idx = _find_col(headers, _RRN_HEADERS)
        if name_idx is None or rrn_idx is None:
            continue

        for row in rows_iter:
            if row is None or name_idx >= len(row) or rrn_idx >= len(row):
                continue
            name_cell = row[name_idx]
            rrn_cell = row[rrn_idx]
            if name_cell is None or rrn_cell is None:
                continue
            name = str(name_cell).strip()
            rrn_raw = str(rrn_cell).strip()
            if not name or not rrn_raw:
                continue
            entry = _entry_from_rrn(rrn_raw)
            if entry is None:
                continue
            # 동일 이름 재출현 시 첫 값 유지 (동명이인은 UI 매칭 실패로 자연 처리)
            result.setdefault(name, entry)
    wb.close()
    return result


def _extract_rrn_map_csv(blob: bytes) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    try:
        text = blob.decode("utf-8-sig", errors="replace")
    except Exception:  # noqa: BLE001
        return result
    reader = csv.reader(io.StringIO(text))
    header_row = next(reader, None)
    if not header_row:
        return result
    headers = [h.strip() for h in header_row]
    name_idx = _find_col(headers, _NAME_HEADERS)
    rrn_idx = _find_col(headers, _RRN_HEADERS)
    if name_idx is None or rrn_idx is None:
        return result
    for row in reader:
        if name_idx >= len(row) or rrn_idx >= len(row):
            continue
        name = row[name_idx].strip()
        rrn_raw = row[rrn_idx].strip()
        if not name or not rrn_raw:
            continue
        entry = _entry_from_rrn(rrn_raw)
        if entry is None:
            continue
        result.setdefault(name, entry)
    return result


def _excel_to_text(blob: bytes) -> str:
    wb = load_workbook(io.BytesIO(blob), data_only=True, read_only=True)
    out_lines: list[str] = []
    for ws in wb.worksheets:
        out_lines.append(f"# Sheet: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = ["" if v is None else str(v) for v in row]
            if any(cells):
                out_lines.append("\t".join(cells))
    return "\n".join(out_lines)


def _csv_to_text(blob: bytes) -> str:
    text = blob.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    return "\n".join("\t".join(row) for row in rows if any(c.strip() for c in row))


async def intake_file(
    *,
    filename: str,
    content: bytes,
    storage: ObjectStorage,
) -> IntakeResult:
    """Turn an uploaded file into plain text suitable for the AI parser."""
    if _is_audio(filename):
        # 음성/통화 처리 미지원 (정책 폐기) — 파일 보관 없이 안내만 반환
        return IntakeResult(
            text="",
            kind="audio",
            note="음성 파일은 현재 처리하지 않습니다.",
        )

    if _is_excel(filename):
        ext = "." + filename.rsplit(".", 1)[-1].lower()
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if ext == ".xlsx" else "application/vnd.ms-excel"
        key = storage.make_key("excel", ext)
        storage.put_object(key, content, content_type=mime)
        rrn_map = _extract_rrn_map_excel(content)
        # 위하고T 22컬럼 급여대장이면 결정론적 파서로 처리 — LLM 컬럼 매핑 실패 회피.
        structured = parse_wehago_workbook(content)
        if structured:
            summary = f"[위하고T 22컬럼 급여대장 감지 — {len(structured)}명]"
            return IntakeResult(
                text=summary,
                kind="excel",
                storage_key=key,
                structured_payroll=structured,
                rrn_map=rrn_map,
            )
        return IntakeResult(
            text=redact_pii(_excel_to_text(content)),
            kind="excel",
            storage_key=key,
            rrn_map=rrn_map,
        )

    if _is_csv(filename):
        key = storage.make_key("csv", ".csv")
        storage.put_object(key, content, content_type="text/csv")
        return IntakeResult(
            text=redact_pii(_csv_to_text(content)),
            kind="csv",
            storage_key=key,
            rrn_map=_extract_rrn_map_csv(content),
        )

    if _is_text(filename):
        key = storage.make_key("text", ".txt")
        storage.put_object(key, content, content_type="text/plain")
        text = content.decode("utf-8-sig", errors="replace")
        return IntakeResult(
            text=redact_pii(text),
            kind="text",
            storage_key=key,
        )

    if _is_image(filename):
        # 이미지는 Object Storage에 보존(감사용) + raw bytes를 함께 반환해
        # AI 파서가 Vision 모델로 직접 분석하도록 한다.
        ext = "." + filename.rsplit(".", 1)[-1].lower()
        mime = _image_mime(ext)
        key = storage.make_key("image", ext)
        storage.put_object(key, content, content_type=mime)
        return IntakeResult(
            text=f"[이미지 첨부: {filename}]",  # AI에 컨텍스트만 제공 — 실제 내용은 images로
            kind="image",
            storage_key=key,
            images=[(content, mime)],
        )

    if _is_pdf(filename):
        # PDF는 원본 보존 + 각 페이지를 PNG로 변환해 Vision 으로 보낸다.
        key = storage.make_key("pdf", ".pdf")
        storage.put_object(key, content, content_type="application/pdf")
        try:
            pages = _pdf_to_page_images(content)
        except Exception as e:  # noqa: BLE001
            logger.exception("[file-intake] PDF parse failed: %s", filename)
            return IntakeResult(
                text=f"[PDF 첨부: {filename} — 페이지 변환 실패]",
                kind="pdf",
                storage_key=key,
                note=f"PDF 변환 오류: {e}",
            )
        if not pages:
            return IntakeResult(
                text=f"[PDF 첨부: {filename} — 페이지 없음]",
                kind="pdf",
                storage_key=key,
                note="빈 PDF",
            )
        return IntakeResult(
            text=f"[PDF 첨부: {filename}, {len(pages)}페이지]",
            kind="pdf",
            storage_key=key,
            images=pages,
        )

    return IntakeResult(text="", kind="unknown", note=f"지원하지 않는 파일 형식: {filename}")


def _image_mime(ext: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")


__all__ = ["IntakeResult", "intake_file"]
