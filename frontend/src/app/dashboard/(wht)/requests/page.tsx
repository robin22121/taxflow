// "자료요청" — 원천세 신고 세부메뉴 1번. 실제 발송 로직은 아직 각 신고 건 상세화면
// (`/dashboard/filings/[id]`)에만 있고, 여기서 어느 귀속월을 기준으로 요청할지는
// 미정이라 우선 플레이스홀더만 둔다 (2026-09-30 확인, plan/08-action-items.md).
export default function RequestsPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-12 text-center">
      <h1 className="text-[18px] font-bold tracking-tight text-gray-900 mb-2">자료요청</h1>
      <p className="text-[13px] text-gray-500">
        이 화면에서 바로 자료요청을 보내는 기능은 준비 중입니다. 지금은 &quot;월별 신고&quot;에서
        신고 건을 선택한 뒤 해당 화면의 자료요청 버튼을 이용해 주세요.
      </p>
    </div>
  );
}
