"use client";

import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Suspense, useEffect, useRef } from "react";

import { Button, Card } from "@/components/ui";
import { useRegisterBilling } from "@/lib/queries";

function SuccessInner() {
  const router = useRouter();
  const sp = useSearchParams();
  const register = useRegisterBilling();
  const started = useRef(false);

  const authKey = sp.get("authKey");
  const customerKey = sp.get("customerKey");
  const plan = sp.get("plan") ?? "STARTER";
  const missingParams = !authKey || !customerKey;

  useEffect(() => {
    if (started.current || missingParams) return;
    started.current = true;
    register.mutate(
      { auth_key: authKey!, customer_key: customerKey!, plan },
      { onSuccess: () => router.replace("/dashboard/billing") },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const errorMsg = missingParams
    ? "결제 인증 정보가 없습니다."
    : register.isError
      ? (register.error as Error).message
      : null;

  return (
    <div className="max-w-md mx-auto mt-16">
      <Card className="p-6 space-y-4 text-center">
        {errorMsg ? (
          <>
            <h1 className="text-[16px] font-bold text-gray-900">
              결제 처리에 실패했습니다
            </h1>
            <p className="text-[13px] text-red-600">{errorMsg}</p>
            <Link href="/dashboard/billing">
              <Button variant="secondary">결제 페이지로 돌아가기</Button>
            </Link>
          </>
        ) : (
          <>
            <h1 className="text-[16px] font-bold text-gray-900">
              카드 등록 및 결제 처리 중...
            </h1>
            <p className="text-[13px] text-gray-500">
              잠시만 기다려주세요. 자동으로 이동합니다.
            </p>
          </>
        )}
      </Card>
    </div>
  );
}

export default function BillingSuccessPage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-md mx-auto mt-16 text-center text-[13px] text-gray-400">
          불러오는 중...
        </div>
      }
    >
      <SuccessInner />
    </Suspense>
  );
}
