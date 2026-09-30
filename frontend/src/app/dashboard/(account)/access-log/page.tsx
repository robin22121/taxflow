"use client";

import { useAccessLog, useMe } from "@/lib/queries";
import { Card } from "@/components/ui";

const ACTION_LABEL: Record<string, string> = {
  LOGIN: "로그인",
  LOGIN_FAILED: "로그인 실패",
  VIEW: "조회",
  EDIT: "수정",
  DOWNLOAD: "다운로드",
  DECRYPT_RRN: "주민번호 열람",
};

export default function AccessLogPage() {
  const { data: me } = useMe();
  const { data: rows = [], isLoading } = useAccessLog();

  if (me && me.role !== "OWNER") {
    return <p className="text-[13px] text-gray-500">대표(세무사) 계정만 접근할 수 있습니다.</p>;
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-[20px] font-bold tracking-tight text-gray-900">접속기록</h1>
        <p className="text-[13px] text-gray-500 mt-0.5">
          최근 로그인·접근 기록입니다(최대 200건). 개인정보 안전성 확보조치 기준에 따라 2년간 보관됩니다.
        </p>
      </div>

      <Card className="p-0 overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-gray-50 border-b border-gray-100">
            <tr>
              <th className="text-left py-2.5 px-4 text-[11px] font-medium text-gray-500 uppercase tracking-wider">시각</th>
              <th className="text-left py-2.5 px-2 text-[11px] font-medium text-gray-500 uppercase tracking-wider">사용자</th>
              <th className="text-left py-2.5 px-2 text-[11px] font-medium text-gray-500 uppercase tracking-wider">동작</th>
              <th className="text-left py-2.5 px-2 text-[11px] font-medium text-gray-500 uppercase tracking-wider">거래처</th>
              <th className="text-left py-2.5 px-4 text-[11px] font-medium text-gray-500 uppercase tracking-wider">IP</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={5} className="text-center py-6 text-gray-400">불러오는 중...</td></tr>
            )}
            {!isLoading && rows.length === 0 && (
              <tr><td colSpan={5} className="text-center py-6 text-gray-400">기록이 없습니다.</td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-gray-50 last:border-0">
                <td className="py-2 px-4 text-gray-500 tabular-nums whitespace-nowrap">
                  {new Date(r.created_at).toLocaleString("ko-KR")}
                </td>
                <td className="py-2 px-2 text-gray-900">{r.user_name ?? "—"}</td>
                <td className="py-2 px-2">
                  <span className={r.action === "LOGIN_FAILED" ? "text-red-600 font-medium" : "text-gray-700"}>
                    {ACTION_LABEL[r.action] ?? r.action}
                  </span>
                </td>
                <td className="py-2 px-2 text-gray-500">{r.client_name ?? "—"}</td>
                <td className="py-2 px-4 text-gray-400 font-mono text-[12px]">{r.ip ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
