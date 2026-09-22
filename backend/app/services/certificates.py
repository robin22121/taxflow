"""증명원 카탈로그·보관 정책 — plan/17-certificate-issuance.md §1·§4-9.

``available=True`` 는 증명발급 에이전트(rpa/certificate-agent ``CERT_SPECS``)가 실제로
발급할 수 있는 종류다. 나머지는 메뉴에 '준비중'으로만 보인다.
``period=True`` 는 기간 입력이 필요한 종류 — 최근 1·3·5년 중 선택(``PERIOD_YEARS``).
"""

from __future__ import annotations

from datetime import datetime, timedelta

# 서버 사본 보관 기간 — 고객 안내문의 "30일간 유효"와 같은 값
RETENTION = timedelta(days=30)

PERIOD_YEARS = (1, 3, 5)

CATEGORY_LABEL = {"HOMETAX": "홈택스", "WETAX": "지방세", "EMPLOYEE": "직원용"}

CATALOG: list[dict] = [
    # 홈택스 즉시발급 (§1 우선순위)
    {"code": "BUSINESS_REGISTRATION", "category": "HOMETAX", "title": "사업자등록증명", "available": True},
    {"code": "TAX_CLEARANCE_ETC", "category": "HOMETAX", "title": "납세증명서(기타용)", "available": True},
    {"code": "TAX_PAYMENT_HISTORY", "category": "HOMETAX", "title": "납부내역증명(납세사실증명)", "available": True, "period": True},
    {"code": "INCOME_AMOUNT", "category": "HOMETAX", "title": "소득금액증명", "available": True, "period": True},
    {"code": "VAT_BASE", "category": "HOMETAX", "title": "부가가치세 과세표준증명", "available": True, "period": True},
    {"code": "VAT_EXEMPT_INCOME", "category": "HOMETAX", "title": "부가가치세 면세사업자 수입금액증명", "available": True,
     "note": "면세사업자만 (사업자번호 4~5번째 자리 80·89·90~99)"},
    {"code": "BUSINESS_CLOSURE", "category": "HOMETAX", "title": "폐업사실증명", "available": True,
     "note": "폐업 이력이 있는 사업자만"},
    # 지방세 (위택스) — 위택스 자동화 전까지 준비중
    {"code": "LOCAL_TAX_CLEARANCE", "category": "WETAX", "title": "지방세 납세증명서", "available": False},
    {"code": "LOCAL_TAX_ASSESSMENT", "category": "WETAX", "title": "지방세 세목별 과세증명서", "available": False},
    {"code": "LOCAL_TAX_PAYMENT", "category": "WETAX", "title": "지방세 납부확인서", "available": False},
    # 직원용 — 신고 화면의 '준비중' 모달을 흡수 (§4-9)
    {"code": "WITHHOLDING_RECEIPT", "category": "EMPLOYEE", "title": "근로소득 원천징수영수증", "available": False},
    {"code": "EMPLOYMENT_CERT", "category": "EMPLOYEE", "title": "재직증명서", "available": True,
     "note": "재직 중인 직원만"},
    {"code": "CAREER_CERT", "category": "EMPLOYEE", "title": "경력증명서", "available": True},
    {"code": "EMPLOYEE_INCOME_AMOUNT", "category": "EMPLOYEE", "title": "소득금액증명원", "available": False},
]

CATALOG_BY_CODE = {c["code"]: c for c in CATALOG}


def delivery_body(office_name: str, business_name: str, items: list[tuple[str, str]], expires_at: datetime) -> str:
    """고객 안내문. items = [(증명원 이름, 다운로드 링크)]. "30일간 유효" 문구 필수 (§4-9)."""
    lines = [f"[{office_name}] {business_name} 증명원 발급 안내", ""]
    for title, url in items:
        lines.append(f"· {title}")
        lines.append(f"  {url}")
    lines.append("")
    lines.append(f"※ 링크는 발급일로부터 30일간 유효합니다 ({expires_at:%Y-%m-%d}까지).")
    return "\n".join(lines)
