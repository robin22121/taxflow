"""file_intake unit tests using LocalFileStorage + StubSTT."""

import io
import tempfile

import pytest
from openpyxl import Workbook

from app.services.file_intake import intake_file
from app.services.storage import LocalFileStorage
from app.services.stt import StubSTT


def _excel_bytes(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_excel_intake_extracts_text():
    blob = _excel_bytes([
        ["성명", "지급액"],
        ["김연호", 1_000_000],
        ["박민수", 1_500_000],
    ])
    with tempfile.TemporaryDirectory() as d:
        res = await intake_file(
            filename="payroll.xlsx",
            content=blob,
            storage=LocalFileStorage(base_dir=d),
            stt=StubSTT(),
        )
    assert res.kind == "excel"
    assert "김연호" in res.text
    assert "1000000" in res.text


@pytest.mark.asyncio
async def test_csv_intake():
    csv_text = "성명,지급액\n김연호,1000000\n박민수,1500000\n"
    blob = b"\xef\xbb\xbf" + csv_text.encode("utf-8")
    with tempfile.TemporaryDirectory() as d:
        res = await intake_file(
            filename="x.csv",
            content=blob,
            storage=LocalFileStorage(base_dir=d),
            stt=StubSTT(),
        )
    assert res.kind == "csv"
    assert "김연호" in res.text
    assert "박민수" in res.text


@pytest.mark.asyncio
async def test_audio_intake_uses_stt_and_redacts_pii():
    stt = StubSTT()
    stt.canned = "신규 직원 박민수 900101-1234567 150만원"
    with tempfile.TemporaryDirectory() as d:
        res = await intake_file(
            filename="call.mp3",
            content=b"fake-audio-bytes",
            storage=LocalFileStorage(base_dir=d),
            stt=stt,
        )
    assert res.kind == "audio"
    assert res.storage_key is not None
    assert res.storage_key.startswith("voice/")
    assert "900101-1234567" not in res.text
    assert "박민수" in res.text


@pytest.mark.asyncio
async def test_image_returns_binary_for_vision():
    content = b"\x89PNG\r\n\x1a\nfake"
    with tempfile.TemporaryDirectory() as d:
        res = await intake_file(
            filename="photo.png",
            content=content,
            storage=LocalFileStorage(base_dir=d),
            stt=StubSTT(),
        )
    assert res.kind == "image"
    assert len(res.images) == 1
    assert res.images[0] == (content, "image/png")
    # 텍스트는 placeholder만 — 실제 OCR은 Vision 모델이 처리
    assert "[이미지 첨부" in res.text


@pytest.mark.asyncio
async def test_pdf_renders_pages_to_images():
    """PDF 첨부는 각 페이지를 PNG로 렌더링해서 images 리스트에 담는다."""
    from PIL import Image

    # 2페이지 PDF 생성
    img1 = Image.new("RGB", (200, 200), "white")
    img2 = Image.new("RGB", (200, 200), "white")
    buf = io.BytesIO()
    img1.save(buf, format="PDF", save_all=True, append_images=[img2])

    with tempfile.TemporaryDirectory() as d:
        res = await intake_file(
            filename="invoice.pdf",
            content=buf.getvalue(),
            storage=LocalFileStorage(base_dir=d),
            stt=StubSTT(),
        )
    assert res.kind == "pdf"
    assert len(res.images) == 2
    for img_bytes, mime in res.images:
        assert mime == "image/png"
        assert img_bytes.startswith(b"\x89PNG")
    assert "2페이지" in res.text


@pytest.mark.asyncio
async def test_unknown_extension():
    with tempfile.TemporaryDirectory() as d:
        res = await intake_file(
            filename="x.bin",
            content=b"x",
            storage=LocalFileStorage(base_dir=d),
            stt=StubSTT(),
        )
    assert res.kind == "unknown"
    assert res.text == ""
