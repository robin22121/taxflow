# 더존 SmartA 보안 모듈 PoC

**목적**: pywinauto가 SmartA 프로세스에 붙을 수 있는지, 필드 입력이 반영되는지 확인.

**판정 기준**:
- 통과 → 원천세 신고서 전체 필드 매핑 착수
- 부분차단 (트리 dump는 되는데 특정 컨트롤 비어있음/입력 무시) → 우회안 탐색
- 완전차단 (프로세스 강제 종료) → RPA 전략 재고

---

## 환경 준비 (Windows)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## Step A. 로컬 학습 (SmartA 없이 pywinauto 자체 검증)

메모장으로 스크립트 동작 확인. 여기서 실패하면 SmartA 이슈가 아니라 환경 이슈.

1. 메모장 실행: `notepad`
2. Attach + dump:
   ```powershell
   python attach.py --title "메모장" --backend uia
   ```
   → `dumps/controls-uia-*.txt` 에 컨트롤 트리 저장됐는지 확인.
3. 텍스트 입력:
   ```powershell
   python probe.py --title "메모장" --control-key class_name --control "Edit" --text "hello"
   ```
   → 메모장에 `hello` 표시되면 OK.

---

## Step B. SmartA 실기 (세무사 PC)

1. SmartA 실행 → 로그인 → 원천세 신고서 화면 진입
2. **UIA backend 시도**:
   ```powershell
   python attach.py --title "SmartA" --backend uia
   ```
   결과 분류:
   - 프로세스 강제 종료 → **완전차단** (Step B 종료, 결과 기록)
   - dump 파일이 극도로 작음 (<200 bytes) → UIA 접근 차단 가능성 → 3번으로
   - dump가 정상 (수 KB 이상) → 4번으로
3. **win32 backend 시도** (UIA 차단 시):
   ```powershell
   python attach.py --title "SmartA" --backend win32
   ```
4. **컨트롤 트리 확인**: `dumps/controls-*.txt` 를 열어서 신고서 필드에 `auto_id` 또는 `title` 이 노출되는지 확인. 없으면 이미지 인식 방식 필요.
5. **입력 시도** (트리에서 확인한 식별자 사용):
   ```powershell
   python probe.py --title "SmartA" --control-key auto_id --control "찾은식별자" --text "테스트"
   ```
   실제 신고 데이터가 아닌 **명백히 테스트임을 알 수 있는 값** 사용 (예: `TESTTESTTEST`).

---

## 결과 기록

각 스텝의 결과·에러 로그·스크린샷을 세무사와 공유하고 판정.

- `dumps/` 폴더는 `.gitignore` 됨 (실기 데이터 유출 방지).
- 공유할 때 개인정보·사업자번호 마스킹.
