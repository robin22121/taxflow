"""Convert uploaded files into the plain-text representation our AI parser expects.

Supported types in Phase 1:
- Audio (.mp3 / .m4a / .wav / .aac) — put to Object Storage, presign URL, send to STT.
- Excel (.xlsx / .xls) — read cells with openpyxl, build a tab-separated text dump.
- CSV (.csv) — decoded as text directly.
- Image (.png / .jpg / .jpeg) — TODO: forward to Claude Vision in a follow-up; for Phase 1
  we attach a placeholder note and return early so the user is asked to retype.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Iterable

from openpyxl import load_workbook

from app.services.pii import redact_pii
from app.services.storage import ObjectStorage
from app.services.stt import STTProvider


AUDIO_EXTS = (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac")
EXCEL_EXTS = (".xlsx", ".xlsm", ".xls")
CSV_EXTS = (".csv",)
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


@dataclass(slots=True)
class IntakeResult:
    text: str
    kind: str  # "audio" | "excel" | "csv" | "image" | "unknown"
    storage_key: str | None = None
    note: str | None = None


def _is_audio(filename: str) -> bool:
    return filename.lower().endswith(AUDIO_EXTS)


def _is_excel(filename: str) -> bool:
    return filename.lower().endswith(EXCEL_EXTS)


def _is_csv(filename: str) -> bool:
    return filename.lower().endswith(CSV_EXTS)


def _is_image(filename: str) -> bool:
    return filename.lower().endswith(IMAGE_EXTS)


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
    stt: STTProvider,
) -> IntakeResult:
    """Turn an uploaded file into plain text suitable for the AI parser."""
    if _is_audio(filename):
        ext = "." + filename.rsplit(".", 1)[-1].lower()
        key = storage.make_key("voice", ext)
        storage.put_object(key, content, content_type=_audio_mime(ext))
        url = storage.presign_url(key, expires_in=3600)
        result = await stt.transcribe(audio_url=url)
        return IntakeResult(
            text=redact_pii(result.text),
            kind="audio",
            storage_key=key,
            note=f"transcribed via {result.provider}",
        )

    if _is_excel(filename):
        return IntakeResult(
            text=redact_pii(_excel_to_text(content)),
            kind="excel",
        )

    if _is_csv(filename):
        return IntakeResult(
            text=redact_pii(_csv_to_text(content)),
            kind="csv",
        )

    if _is_image(filename):
        # TODO: route to Claude Vision in a follow-up. For now we store the file
        # for human review and return a placeholder so the session is flagged.
        ext = "." + filename.rsplit(".", 1)[-1].lower()
        key = storage.make_key("image", ext)
        storage.put_object(key, content, content_type=_image_mime(ext))
        return IntakeResult(
            text="[이미지 업로드 — 사람 확인 필요]",
            kind="image",
            storage_key=key,
            note="Claude Vision 연동 전: 세무사가 이미지를 직접 확인해주세요",
        )

    return IntakeResult(text="", kind="unknown", note=f"지원하지 않는 파일 형식: {filename}")


def _audio_mime(ext: str) -> str:
    return {
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }.get(ext, "application/octet-stream")


def _image_mime(ext: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")


__all__ = ["IntakeResult", "intake_file"]
