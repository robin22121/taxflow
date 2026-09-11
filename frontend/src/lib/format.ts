/** 숫자만 추출 */
export function digitsOnly(v: string): string {
  return v.replace(/\D/g, "");
}

/** 전화번호 포맷: 01012345678 → 010-1234-5678, 0212345678 → 02-1234-5678 */
export function formatPhone(raw: string): string {
  const d = digitsOnly(raw);
  if (d.startsWith("02")) {
    if (d.length <= 2) return d;
    if (d.length <= 5) return `${d.slice(0, 2)}-${d.slice(2)}`;
    if (d.length <= 9) return `${d.slice(0, 2)}-${d.slice(2, 5)}-${d.slice(5)}`;
    return `${d.slice(0, 2)}-${d.slice(2, 6)}-${d.slice(6, 10)}`;
  }
  if (d.length <= 3) return d;
  if (d.length <= 7) return `${d.slice(0, 3)}-${d.slice(3)}`;
  return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7, 11)}`;
}

/** 사업자번호 포맷: 1234567890 → 123-45-67890 */
export function formatBizNumber(raw: string): string {
  const d = digitsOnly(raw);
  if (d.length <= 3) return d;
  if (d.length <= 5) return `${d.slice(0, 3)}-${d.slice(3)}`;
  return `${d.slice(0, 3)}-${d.slice(3, 5)}-${d.slice(5, 10)}`;
}

/** 이번 달 기준 직전 월 (귀속월 기본값) — "2026-08" */
export function previousPeriod(): string {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** 주어진 귀속월의 직전 월 — 백엔드 _prev_period와 같은 규칙 */
export function priorPeriod(period: string): string {
  const [y, m] = period.split("-").map(Number);
  const d = new Date(y, m - 2, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** "2026-08" → "2026년 8월분" */
export function koreanPeriod(period: string): string {
  const [y, m] = period.split("-");
  return `${y}년 ${Number(m)}월분`;
}
