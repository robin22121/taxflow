"""Group anomalies / new-hire / resignation suspicions into one follow-up message
and send via the configured channel.
"""

from __future__ import annotations

from typing import Iterable

from app.channels import MessageRecipient, get_alimtalk_channel
from app.channels.base import SendResult
from app.services.matching import MatchingResult


def _format_message(
    client_name: str,
    matching: MatchingResult,
    rrn_url_per_name: dict[str, str],
) -> str:
    lines = [f"[{client_name}] 확인이 필요한 사항이 있습니다 ✋", ""]
    n = 1

    for nh in matching.new_hire_followups:
        url = rrn_url_per_name.get(nh["name"], "(URL 발급 실패)")
        lines.append(
            f"{n}. {nh['name']}님 — 신규 입사자이신가요? 맞다면 아래에서 주민번호·입사일 입력:"
        )
        lines.append(f"   🔗 {url}")
        lines.append("")
        n += 1

    for entry in matching.entries:
        if entry.followup_reason == "amount_change" and entry.anomaly_notes.get("large_change"):
            chg = entry.anomaly_notes["large_change"]
            lines.append(
                f"{n}. {entry.raw_name}님 — 전월 {chg['prev']:,}원 → 이번달 {chg['current']:,}원 "
                f"({chg['ratio']}배). 사유를 알려주세요."
            )
            lines.append("")
            n += 1

    for r in matching.resignation_followups:
        lines.append(
            f"{n}. {r['name']}님 — 이번달 자료에 빠져있어요. 퇴사하셨나요? ({r['reason']})"
        )
        lines.append("")
        n += 1

    for amb in matching.ambiguous_followups:
        lines.append(f"{n}. \"{amb['raw_text']}\" — {amb['issue']}")
        lines.append("")
        n += 1

    return "\n".join(lines).rstrip() if n > 1 else ""


async def send_followup(
    *,
    client_name: str,
    contact_phone: str | None,
    contact_email: str | None,
    matching: MatchingResult,
    rrn_url_per_name: dict[str, str],
) -> SendResult | None:
    """Compose and send a follow-up message. Returns ``None`` if nothing to ask."""
    body = _format_message(client_name, matching, rrn_url_per_name)
    if not body:
        return None
    channel = get_alimtalk_channel()
    return await channel.send(
        MessageRecipient(name=client_name, phone=contact_phone, email=contact_email),
        body=body,
        template_code="FOLLOWUP_PAYROLL",
    )


__all__ = ["send_followup"]
