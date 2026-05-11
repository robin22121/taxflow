"""AES-256-GCM encryption for sensitive PII (주민번호 등).

Key handling:
- ``rrn_encryption_key`` setting holds a base64-encoded 32-byte key.
- In dev a random key is generated on import if not supplied (data won't survive restarts).
- In prod the key MUST come from a KMS-backed secret store.
"""

from __future__ import annotations

import base64
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings


def _load_key() -> bytes:
    settings = get_settings()
    raw = settings.rrn_encryption_key
    if raw:
        try:
            key = base64.b64decode(raw)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError("RRN_ENCRYPTION_KEY must be base64-encoded 32 bytes") from e
        if len(key) != 32:
            raise RuntimeError("RRN_ENCRYPTION_KEY must decode to exactly 32 bytes")
        return key

    if settings.app_env == "dev":
        # dev fallback: persist a random key to .dev_rrn_key so it survives restarts.
        from pathlib import Path
        key_file = Path(__file__).resolve().parent.parent.parent / ".dev_rrn_key"
        if key_file.exists():
            return base64.b64decode(key_file.read_text().strip())
        key = secrets.token_bytes(32)
        key_file.write_text(base64.b64encode(key).decode())
        return key

    raise RuntimeError("RRN_ENCRYPTION_KEY required outside dev")


_KEY = _load_key()
_AESGCM = AESGCM(_KEY)


def encrypt_rrn(plaintext: str) -> bytes:
    """Encrypt 주민번호 → 12-byte nonce || ciphertext+tag."""
    if not plaintext:
        return b""
    nonce = os.urandom(12)
    ct = _AESGCM.encrypt(nonce, plaintext.encode("utf-8"), associated_data=b"rrn")
    return nonce + ct


def decrypt_rrn(blob: bytes) -> str:
    """Decrypt to plaintext 주민번호."""
    if not blob:
        return ""
    nonce, ct = blob[:12], blob[12:]
    return _AESGCM.decrypt(nonce, ct, associated_data=b"rrn").decode("utf-8")


def mask_rrn(plaintext: str) -> str:
    """``900101-1234567`` → ``900101-1******``."""
    if not plaintext or len(plaintext) < 8:
        return "******"
    return plaintext[:8] + "*" * 6


def random_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)
