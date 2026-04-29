import tempfile
from pathlib import Path

from app.services.storage import LocalFileStorage


def test_local_put_get_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        s = LocalFileStorage(base_dir=d)
        key = s.make_key("test", ".bin")
        url = s.put_object(key, b"hello")
        assert url.startswith("file://")
        assert s.get_object(key) == b"hello"


def test_local_make_key_partitioning():
    s = LocalFileStorage(base_dir=tempfile.mkdtemp())
    k1 = s.make_key("voice", ".mp3")
    k2 = s.make_key("voice", ".mp3")
    assert k1 != k2
    assert k1.startswith("voice/")
    assert k1.endswith(".mp3")


def test_local_presign_returns_file_path():
    with tempfile.TemporaryDirectory() as d:
        s = LocalFileStorage(base_dir=d)
        key = s.make_key("test")
        s.put_object(key, b"x")
        url = s.presign_url(key)
        assert url.startswith("file://")
        assert Path(url[7:]).exists()
