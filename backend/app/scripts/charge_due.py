"""매월 정기결제 — next_billing_date 가 도래한 구독을 일괄 청구.

Celery 미구성 + Render+Vercel 배포 환경이라, 별도 워커/beat 인프라 대신
멱등 스크립트로 구현. (기존 ``python -m app.scripts.seed`` 운용 패턴과 동일)

Run::
    python -m app.scripts.charge_due

운영: Render Cron Job(매일 1회)에서 이 스크립트를 실행하거나,
외부 스케줄러가 ``POST /api/v1/billing/cron/charge-due`` (X-Cron-Secret) 를
호출해도 동일하게 동작한다. 이미 결제된 회차는 next_billing_date 가
미래로 밀리므로 중복 청구되지 않는다(멱등).
"""

from __future__ import annotations

import asyncio
import logging

from app.db import SessionLocal
from app.services.billing import charge_due_subscriptions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def _main() -> None:
    async with SessionLocal() as db:
        result = await charge_due_subscriptions(db)
    logger.info(
        "정기결제 완료 — charged=%s failed=%s", result["charged"], result["failed"]
    )
    for line in result["details"]:
        logger.info("  %s", line)


if __name__ == "__main__":
    asyncio.run(_main())
