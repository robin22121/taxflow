"""시뮬레이션: 12개 샘플 파일 → file_intake → AI 파싱 → 매칭 엔진.

Usage:
    cd backend && python -m scripts.simulate_parsing
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# backend 패키지를 임포트할 수 있도록 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.ai_parser import parse_payroll_message
from app.services.file_intake import _excel_to_text, _csv_to_text
from app.models.payroll import MatchStatus
from app.services.matching import EmployeeMaster, reconcile

DATA_DIR = Path(os.path.expanduser("~/Downloads/data"))

# ── 거래처별 가상 직원 마스터 + 전월 데이터 ──────────────────────────

SCENARIOS: dict[str, dict] = {
    "01_하늘식품": {
        "master": [
            EmployeeMaster(id="E001", name="박정수", last_amount=5400000),
            EmployeeMaster(id="E002", name="김미영", last_amount=4800000),
            EmployeeMaster(id="E003", name="이준호", last_amount=3700000),
            EmployeeMaster(id="E004", name="최서연", last_amount=3300000),
            EmployeeMaster(id="E005", name="한동욱", last_amount=2700000),
            EmployeeMaster(id="E006", name="정하늘", last_amount=2500000),
        ],
        "prev": {"E001": 5400000, "E002": 4800000, "E003": 3700000,
                 "E004": 3300000, "E005": 2700000, "E006": 2500000},
    },
    "02_카페모닝": {
        "master": [
            EmployeeMaster(id="E010", name="김갑수", last_amount=2000000),
            EmployeeMaster(id="E011", name="이태리", last_amount=1800000),
            EmployeeMaster(id="E012", name="박소현", last_amount=2200000),
        ],
        "prev": {"E010": 2000000, "E011": 1800000, "E012": 2200000},
    },
    "03_성진건설": {
        "master": [
            EmployeeMaster(id="E020", name="김성진", last_amount=3500000),
            EmployeeMaster(id="E021", name="오세현", last_amount=2800000),
            EmployeeMaster(id="E022", name="장도윤", last_amount=2800000),
            EmployeeMaster(id="E023", name="이민재", last_amount=2500000),
        ],
        "prev": {"E020": 3500000, "E021": 2800000, "E022": 2800000, "E023": 2500000},
    },
    "04_미소약국": {
        "master": [
            EmployeeMaster(id="E030", name="박미소", last_amount=3000000),
            EmployeeMaster(id="E031", name="김약사", last_amount=4000000),
            EmployeeMaster(id="E032", name="이보조", last_amount=2200000),
        ],
        "prev": {"E030": 3000000, "E031": 4000000, "E032": 2200000},
    },
    "05_대한물류": {
        "master": [
            EmployeeMaster(id="E040", name="강태호", last_amount=4350000),
            EmployeeMaster(id="E041", name="윤서진", last_amount=3500000),
            EmployeeMaster(id="E042", name="배수빈", last_amount=2900000),
            EmployeeMaster(id="E043", name="노건우", last_amount=2700000),
            EmployeeMaster(id="E044", name="송미래", last_amount=2200000),
        ],
        "prev": {"E040": 4350000, "E041": 3500000, "E042": 2900000,
                 "E043": 2700000, "E044": 2200000},
    },
    "06_헤어봄": {
        "master": [
            EmployeeMaster(id="E050", name="김갑수", last_amount=2000000),
        ],
        "prev": {"E050": 2000000},
    },
    "07_넥스트코드": {
        "master": [
            EmployeeMaster(id="E060", name="정민석", last_amount=4500000),
            EmployeeMaster(id="E061", name="한소희", last_amount=3800000),
            EmployeeMaster(id="E062", name="오준영", last_amount=3200000),
            EmployeeMaster(id="E063", name="이가은", last_amount=2800000),
        ],
        "prev": {"E060": 4500000, "E061": 3800000, "E062": 3200000, "E063": 2800000},
    },
    "08_맛나분식": {
        "master": [
            EmployeeMaster(id="E070", name="이맛나", last_amount=3000000),
            EmployeeMaster(id="E071", name="김철수", last_amount=2800000),
            EmployeeMaster(id="E072", name="박영희", last_amount=2000000),
            EmployeeMaster(id="E073", name="정민호", last_amount=1200000),
        ],
        "prev": {"E070": 3000000, "E071": 2800000, "E072": 2000000, "E073": 1200000},
    },
    "09_삼광테크": {
        "master": [
            EmployeeMaster(id="E080", name="임광호", last_amount=4000000),
            EmployeeMaster(id="E081", name="서동현", last_amount=3400000),
            EmployeeMaster(id="E082", name="이현정", last_amount=3000000),
            EmployeeMaster(id="E083", name="김태양", last_amount=3400000),
            EmployeeMaster(id="E084", name="박은서", last_amount=2800000),
            EmployeeMaster(id="E085", name="최형준", last_amount=2600000),
            EmployeeMaster(id="E086", name="남궁민", last_amount=2600000),
            EmployeeMaster(id="E087", name="장서윤", last_amount=2400000),
        ],
        "prev": {"E080": 4000000, "E081": 3400000, "E082": 3000000, "E083": 3400000,
                 "E084": 2800000, "E085": 2600000, "E086": 2600000, "E087": 2400000},
    },
    "10_황금식당": {
        "master": [
            EmployeeMaster(id="E090", name="황금자", last_amount=2500000),
            EmployeeMaster(id="E091", name="김순이", last_amount=2100000),
            EmployeeMaster(id="E092", name="최영자", last_amount=1900000),
        ],
        "prev": {"E090": 2500000, "E091": 2100000, "E092": 1900000},
    },
    "11_법무법인정의": {
        "master": [
            EmployeeMaster(id="E100", name="하정의", last_amount=8400000),
            EmployeeMaster(id="E101", name="김법률", last_amount=6200000),
            EmployeeMaster(id="E102", name="이공정", last_amount=5700000),
            EmployeeMaster(id="E103", name="박신뢰", last_amount=3700000),
            EmployeeMaster(id="E104", name="최성실", last_amount=3000000),
            EmployeeMaster(id="E105", name="강노력", last_amount=2700000),
        ],
        "prev": {"E100": 8400000, "E101": 6200000, "E102": 5700000,
                 "E103": 3700000, "E104": 3000000, "E105": 2700000},
    },
    "12_세븐마트": {
        "master": [
            EmployeeMaster(id="E110", name="김영수", last_amount=2400000),
            EmployeeMaster(id="E111", name="김영수", last_amount=2200000),
            EmployeeMaster(id="E112", name="이미숙", last_amount=2000000),
            EmployeeMaster(id="E113", name="박정환", last_amount=2100000),
            EmployeeMaster(id="E114", name="최수진", last_amount=1800000),
            EmployeeMaster(id="E115", name="홍길동", last_amount=1900000),
        ],
        "prev": {"E110": 2400000, "E111": 2200000, "E112": 2000000,
                 "E113": 2100000, "E114": 1800000, "E115": 1900000},
    },
}


def _load_file(path: Path) -> str:
    """파일을 텍스트로 변환."""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm", ".xls"):
        return _excel_to_text(path.read_bytes())
    elif suffix == ".csv":
        return _csv_to_text(path.read_bytes())
    elif suffix == ".txt":
        return path.read_text(encoding="utf-8")
    else:
        return path.read_text(encoding="utf-8", errors="replace")


def _scenario_key(filename: str) -> str | None:
    """파일명에서 시나리오 키 추출: '01_하늘식품_...' → '01_하늘식품'."""
    parts = filename.split("_", 2)
    if len(parts) >= 2:
        return f"{parts[0]}_{parts[1]}"
    return None


def _master_to_dicts(master: list[EmployeeMaster]) -> list[dict]:
    return [
        {"id": e.id, "name": e.name, "last_amount": e.last_amount}
        for e in master
    ]


def _prev_to_dicts(prev: dict[str, int], master: list[EmployeeMaster]) -> list[dict]:
    by_id = {e.id: e for e in master}
    return [
        {"employee_id": eid, "name": by_id[eid].name, "amount": amt}
        for eid, amt in prev.items()
        if eid in by_id
    ]


async def run_one(filepath: Path) -> dict:
    """단일 파일 시뮬레이션."""
    key = _scenario_key(filepath.stem)
    scenario = SCENARIOS.get(key)
    if not scenario:
        return {"file": filepath.name, "error": f"No scenario for key={key}"}

    master = scenario["master"]
    prev = scenario["prev"]

    # 1. 파일 → 텍스트
    text = _load_file(filepath)

    # 2. AI 파싱
    parsed = await parse_payroll_message(
        text,
        client_name=key.split("_", 1)[1] if "_" in key else key,
        employee_master=_master_to_dicts(master),
        previous_month_data=_prev_to_dicts(prev, master),
        period="2026-04",
    )

    # 3. 매칭 엔진
    matched = reconcile(parsed, master, prev)

    # 4. 결과 정리
    result = {
        "file": filepath.name,
        "input_preview": text[:200] + ("..." if len(text) > 200 else ""),
        "ai_parsing": {
            "matched": [
                {"name": m.name, "employee_id": m.employee_id, "amount": m.amount,
                 "income_type": m.income_type, "non_taxable": m.non_taxable}
                for m in parsed.matched_employees
            ],
            "new_hire": [
                {"name": n.name, "amount": n.amount, "income_type": n.income_type}
                for n in parsed.new_hire_suspected
            ],
            "resignation": [
                {"name": r.name, "reason": r.reason}
                for r in parsed.resignation_suspected
            ],
            "ambiguous": [
                {"raw_text": a.raw_text, "issue": a.issue}
                for a in parsed.ambiguous_items
            ],
            "relative_refs": [
                {"text": r.text, "applied": r.applied}
                for r in parsed.relative_references
            ],
        },
        "matching": {
            "entries": [
                {
                    "name": e.raw_name,
                    "employee_id": e.employee_id,
                    "status": e.match_status.value,
                    "amount": e.total_amount,
                    "income_type": e.income_type.value,
                    "prev_amount": e.prev_amount,
                    "anomaly": e.anomaly_notes if e.anomaly_notes else None,
                    "followup": e.followup_reason,
                }
                for e in matched.entries
            ],
            "new_hire_followups": matched.new_hire_followups,
            "resignation_followups": matched.resignation_followups,
            "ambiguous_followups": matched.ambiguous_followups,
            "unconfirmed_followups": matched.unconfirmed_followups,
        },
        "summary": {
            "total_entries": len(matched.entries),
            "matched": sum(1 for e in matched.entries if e.match_status == MatchStatus.MATCHED),
            "new_hire": len(matched.new_hire_followups),
            "resignation": len(matched.resignation_followups),
            "unconfirmed": len(matched.unconfirmed_followups),
            "ambiguous": len(matched.ambiguous_followups),
            "needs_followup": sum(1 for e in matched.entries if e.needs_followup),
        },
    }
    return result


async def main():
    files = sorted(DATA_DIR.glob("*"))
    if not files:
        print(f"No files found in {DATA_DIR}")
        return

    print(f"{'='*70}")
    print(f"  이지원천 — 수집·파싱 시뮬레이션 ({len(files)}개 파일)")
    print(f"{'='*70}\n")

    all_results = []
    for i, f in enumerate(files):
        if f.name.startswith(".") or f.suffix == ".json":
            continue
        print(f"[{f.name}] 처리 중...", end=" ", flush=True)
        try:
            result = await run_one(f)
            all_results.append(result)

            s = result.get("summary", {})
            if "error" in result:
                print(f"ERROR: {result['error']}")
            else:
                print(
                    f"OK — "
                    f"매칭 {s['matched']}명 | "
                    f"신규 {s['new_hire']}명 | "
                    f"퇴사 {s['resignation']}명 | "
                    f"미확인 {s['unconfirmed']}명 | "
                    f"모호 {s['ambiguous']}건 | "
                    f"확인필요 {s['needs_followup']}건"
                )
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                print("rate limit — 50초 대기 후 재시도...", end=" ", flush=True)
                await asyncio.sleep(50)
                try:
                    result = await run_one(f)
                    all_results.append(result)
                    s = result.get("summary", {})
                    print(
                        f"OK — "
                        f"매칭 {s['matched']}명 | "
                        f"신규 {s['new_hire']}명 | "
                        f"퇴사 {s['resignation']}명 | "
                        f"미확인 {s['unconfirmed']}명 | "
                        f"모호 {s['ambiguous']}건 | "
                        f"확인필요 {s['needs_followup']}건"
                    )
                    continue
                except Exception as e2:
                    print(f"FAIL (retry): {e2}")
                    all_results.append({"file": f.name, "error": str(e2)})
            else:
                print(f"FAIL: {e}")
                all_results.append({"file": f.name, "error": err_str})

    # 상세 결과 저장
    output_path = DATA_DIR / "simulation_result.json"
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(all_results, fp, ensure_ascii=False, indent=2)

    # 요약 출력
    print(f"\n{'='*70}")
    print("  요약")
    print(f"{'='*70}")
    print(f"{'파일':<40} {'매칭':>4} {'신규':>4} {'퇴사':>4} {'미확인':>5} {'모호':>4} {'확인필요':>6}")
    print("-" * 70)
    for r in all_results:
        if "error" in r and "summary" not in r:
            print(f"{r['file']:<40} ERROR: {r['error']}")
            continue
        s = r["summary"]
        print(
            f"{r['file']:<40} "
            f"{s['matched']:>4} "
            f"{s['new_hire']:>4} "
            f"{s['resignation']:>4} "
            f"{s['unconfirmed']:>5} "
            f"{s['ambiguous']:>4} "
            f"{s['needs_followup']:>6}"
        )

    print(f"\n상세 결과: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
