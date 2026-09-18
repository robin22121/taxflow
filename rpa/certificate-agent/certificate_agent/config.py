"""자격증명·설정 저장 (Windows 자격 증명 관리자 via keyring/DPAPI). plan/17 §3-9-6."""

from __future__ import annotations

from dataclasses import dataclass

import keyring

SERVICE = "easyone-cert-agent"

KEYS = [
    "hometax_id",
    "hometax_pw",
    "hometax_rrn_prefix",
    "hometax_rrn_suffix",
    "agent_token",
    "server_url",
]


@dataclass
class AgentConfig:
    hometax_id: str
    hometax_pw: str
    hometax_rrn_prefix: str
    hometax_rrn_suffix: str
    agent_token: str
    server_url: str


def save(key: str, value: str) -> None:
    keyring.set_password(SERVICE, key, value)


def load(key: str) -> str | None:
    return keyring.get_password(SERVICE, key)


def load_all() -> AgentConfig | None:
    values = {k: load(k) for k in KEYS}
    if not all(values.values()):
        return None
    return AgentConfig(**values)  # type: ignore[arg-type]


def clear() -> None:
    for k in KEYS:
        try:
            keyring.delete_password(SERVICE, k)
        except keyring.errors.PasswordDeleteError:
            pass
