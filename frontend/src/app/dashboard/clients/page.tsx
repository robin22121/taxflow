"use client";

import { useClients } from "@/lib/queries";
import { Card } from "@/components/ui";

export default function ClientsPage() {
  const { data, isLoading } = useClients();
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">거래처 관리</h1>
      {isLoading && <p>로딩 중...</p>}
      <div className="grid gap-3">
        {(data ?? []).map((c) => (
          <Card key={c.id}>
            <div className="flex items-baseline gap-3">
              <div className="text-lg font-medium">{c.business_name}</div>
              {c.business_number && (
                <span className="text-xs text-gray-500">{c.business_number}</span>
              )}
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              {[c.representative, c.contact_phone, c.contact_email].filter(Boolean).join(" · ") || "—"}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
