"use client";

import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Suspense } from "react";

import { Button, Card } from "@/components/ui";

function FailInner() {
  const sp = useSearchParams();
  const code = sp.get("code");
  const message = sp.get("message");

  return (
    <div className="max-w-md mx-auto mt-16">
      <Card className="p-6 space-y-4 text-center">
        <h1 className="text-[16px] font-bold text-gray-900">
          카드 등록이 취소되었습니다
        </h1>
        <p className="text-[13px] text-gray-500">
          {message ?? "결제 인증 과정에서 중단되었습니다."}
          {code && (
            <span className="block text-[11px] text-gray-400 mt-1">
              코드: {code}
            </span>
          )}
        </p>
        <Link href="/dashboard/billing">
          <Button variant="secondary">결제 페이지로 돌아가기</Button>
        </Link>
      </Card>
    </div>
  );
}

export default function BillingFailPage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-md mx-auto mt-16 text-center text-[13px] text-gray-400">
          불러오는 중...
        </div>
      }
    >
      <FailInner />
    </Suspense>
  );
}
