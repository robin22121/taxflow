from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from easyone_agent.wehago_employees import EmployeeExportError, parse_employee_export

# 위하고 사원등록 [사원자료 엑셀변환] 실제 헤더 (2026-09-23 서도 실측, 49열)
HEADER = [
    "사원코드", "사원명", "내외국인구분", "거주지국코드", "거주지명", "국적코드", "국가명",
    "주민(외국인)등록번호", "나이", "성별", "입사일자", "퇴사일자", "거주구분", "우편번호", "주소",
    "부서", "직급", "직종", "호봉", "프로젝트", "현장", "건강보험대상금액", "건강보험료",
    "건강보험증번호", "국민연금대상금액", "국민연금료", "고용보험대상금액", "고용보험료",
    "고용보험적용여부", "산재보험적용여부", "장기요양보험적용여부", "생산직여부", "국외근로적용여부",
    "학자금상환공제자여부", "학자금상환공제액", "중소기업청년소득세감면여부", "전화번호", "휴대폰번호",
    "이메일", "급여이체은행", "계좌번호", "예금주", "배우자유무", "20세이하", "60세이상", "경로우대",
    "장애인", "부녀자", "비고",
]


def _row(**values):
    row = [""] * len(HEADER)
    for col, value in values.items():
        row[HEADER.index(col)] = value
    return row


def _xlsx(tmp_path: Path, rows: list[list]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
    path = tmp_path / "서도_사원등록.xlsx"
    wb.save(path)
    return path


def test_only_basic_fields_are_extracted(tmp_path: Path):
    path = _xlsx(tmp_path, [
        _row(**{"사원코드": "1", "사원명": "한지민", "주민(외국인)등록번호": "600915-2000001",
                "입사일자": "20200101", "퇴사일자": "", "직급": "직급없음", "부서": "총무부",
                "계좌번호": "110-123-456789", "휴대폰번호": "010-1234-5678", "주소": "서울"}),
        _row(**{"사원코드": "2", "사원명": "오세훈", "입사일자": "20200101", "퇴사일자": "20260131",
                "직급": "대리"}),
        _row(),  # 빈 행
    ])

    rows = parse_employee_export(path)

    assert rows == [
        {"employee_code": "1", "name": "한지민", "rrn": "600915-2000001", "hired_at": "2020-01-01",
         "resigned_at": None, "department": "총무부", "position": None, "job_type": None},
        {"employee_code": "2", "name": "오세훈", "rrn": None, "hired_at": "2020-01-01",
         "resigned_at": "2026-01-31", "department": None, "position": "대리", "job_type": None},
    ]
    # 계좌·연락처·주소는 서버로 가는 값에 없다
    assert "110-123-456789" not in str(rows) and "010-1234-5678" not in str(rows)


def test_unexpected_format_raises(tmp_path: Path):
    wb = Workbook()
    wb.active.append(["코드", "이름"])
    path = tmp_path / "x.xlsx"
    wb.save(path)
    with pytest.raises(EmployeeExportError):
        parse_employee_export(path)
