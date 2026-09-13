export function formatKrw(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${Math.round(n).toLocaleString("ko-KR")}원`;
}

export function formatKrwCompact(n: number | null | undefined): string {
  if (n == null) return "—";
  const abs = Math.abs(n);
  if (abs >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억원`;
  if (abs >= 10_000) return `${(n / 10_000).toFixed(0)}만원`;
  return formatKrw(n);
}

export function periodLabel(period: string | null | undefined): string {
  if (!period) return "";
  const [y, m] = period.split("-");
  return `${y}년 ${Number(m)}월`;
}

export function periodShort(period: string): string {
  return `${Number(period.slice(5, 7))}월`;
}

export function incomeTypeLabel(t: string | null | undefined): string {
  switch (t) {
    case "WAGE":
      return "근로";
    case "BUSINESS":
      return "사업";
    case "DAILY":
      return "일용";
    case "RETIREMENT":
      return "퇴직";
    case "OTHER":
      return "기타";
    default:
      return "—";
  }
}

export function dDay(dateStr: string | null | undefined, today = new Date()): string {
  if (!dateStr) return "";
  const target = new Date(dateStr);
  const diff = Math.ceil(
    (target.getTime() - new Date(today.toDateString()).getTime()) / (1000 * 60 * 60 * 24),
  );
  if (diff === 0) return "D-day";
  if (diff > 0) return `D-${diff}`;
  return `D+${Math.abs(diff)}`;
}

export function initials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  // 한글 이름은 성 제외 이름 첫 글자, 영문은 이니셜 2자
  if (/^[a-zA-Z\s]+$/.test(trimmed)) {
    const parts = trimmed.split(/\s+/);
    if (parts.length === 1) return parts[0][0]!.toUpperCase();
    return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
  }
  return trimmed.slice(-2);
}

export function avatarTone(name: string): "blue" | "mint" | "violet" | "amber" | "rose" {
  const tones = ["blue", "mint", "violet", "amber", "rose"] as const;
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return tones[Math.abs(hash) % tones.length];
}
