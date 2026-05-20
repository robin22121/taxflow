"""토스페이먼츠 — 카드 빌링키 발급 + 정기결제 승인.

결제수단은 '카드' 빌링키 단일. 인증은 시크릿 키 Basic Auth
(`base64(secretKey + ":")`).
"""

from __future__ import annotations

import base64
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class TossError(RuntimeError):
    """토스 API 오류 — code/message/HTTP status 보존."""

    def __init__(self, code: str, message: str, status_code: int = 0) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status_code = status_code


def _auth_header() -> dict[str, str]:
    s = get_settings()
    if not s.toss_secret_key:
        raise TossError("CONFIG", "TOSS_SECRET_KEY 가 설정되지 않았습니다")
    token = base64.b64encode(f"{s.toss_secret_key}:".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


async def issue_billing_key(*, auth_key: str, customer_key: str) -> dict:
    """카드 등록 인증(authKey) → 빌링키 발급.

    응답에 billingKey, card{company,number,cardType} 등 포함.
    """
    s = get_settings()
    async with httpx.AsyncClient(timeout=30.0) as cli:
        resp = await cli.post(
            f"{s.toss_api_base}/v1/billing/authorizations/issue",
            headers=_auth_header(),
            json={"authKey": auth_key, "customerKey": customer_key},
        )
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        data = {}
    if resp.status_code != 200:
        raise TossError(
            data.get("code", "UNKNOWN"),
            data.get("message", resp.text[:200]),
            resp.status_code,
        )
    return data


async def charge_billing_key(
    *,
    billing_key: str,
    customer_key: str,
    amount: int,
    order_id: str,
    order_name: str,
    customer_email: str | None = None,
    customer_name: str | None = None,
) -> dict:
    """빌링키로 정기결제 1건 승인.

    응답에 paymentKey, method, approvedAt, receipt{url} 등 포함.
    """
    s = get_settings()
    if not billing_key:
        raise TossError("NO_BILLING_KEY", "빌링키가 없습니다 (카드 미등록)")
    payload: dict = {
        "customerKey": customer_key,
        "amount": amount,
        "orderId": order_id,
        "orderName": order_name,
    }
    if customer_email:
        payload["customerEmail"] = customer_email
    if customer_name:
        payload["customerName"] = customer_name
    async with httpx.AsyncClient(timeout=30.0) as cli:
        resp = await cli.post(
            f"{s.toss_api_base}/v1/billing/{billing_key}",
            headers=_auth_header(),
            json=payload,
        )
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        data = {}
    if resp.status_code != 200:
        raise TossError(
            data.get("code", "UNKNOWN"),
            data.get("message", resp.text[:200]),
            resp.status_code,
        )
    return data
