"use client";

import Script from "next/script";
import { useState } from "react";

import { Badge, Button, Card } from "@/components/ui";
import {
  useBillingPlans,
  useCancelSubscription,
  useChangePlan,
  usePayments,
  useRetryPayment,
  useSubscription,
} from "@/lib/queries";

const CLIENT_KEY = process.env.NEXT_PUBLIC_TOSS_CLIENT_KEY ?? "";

type TossBillingAuth = {
  requestBillingAuth: (
    method: string,
    opts: { customerKey: string; successUrl: string; failUrl: string },
  ) => Promise<void>;
};
type TossPaymentsCtor = (clientKey: string) => TossBillingAuth;

function getToss(): TossPaymentsCtor | null {
  if (typeof window === "undefined") return null;
  return (
    (window as unknown as { TossPayments?: TossPaymentsCtor }).TossPayments ??
    null
  );
}

function won(n: number): string {
  return `${n.toLocaleString("ko-KR")}원`;
}

const STATUS_META: Record<
  string,
  { label: string; tone: "neutral" | "success" | "warning" | "danger" }
> = {
  INACTIVE: { label: "카드 미등록", tone: "neutral" },
  ACTIVE: { label: "이용중", tone: "success" },
  PAST_DUE: { label: "결제 실패", tone: "danger" },
  CANCELED: { label: "해지됨", tone: "warning" },
};

export default function BillingPage() {
  const { data: sub, isLoading } = useSubscription();
  const { data: plans } = useBillingPlans();
  const { data: payments } = usePayments();
  const changePlan = useChangePlan();
  const cancelSub = useCancelSubscription();
  const retry = useRetryPayment();

  const [sdkReady, setSdkReady] = useState(false);
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function registerCard(planCode: string) {
    setErr(null);
    if (!CLIENT_KEY) {
      setErr(
        "NEXT_PUBLIC_TOSS_CLIENT_KEY 환경변수가 설정되지 않았습니다 (관리자 문의).",
      );
      return;
    }
    const ctor = getToss();
    if (!ctor || !sub) {
      setErr("결제 모듈 로딩 중입니다. 잠시 후 다시 시도해주세요.");
      return;
    }
    setBusyPlan(planCode);
    try {
      const origin = window.location.origin;
      const toss = ctor(CLIENT_KEY);
      await toss.requestBillingAuth("카드", {
        customerKey: sub.customer_key,
        successUrl: `${origin}/dashboard/billing/success?plan=${planCode}`,
        failUrl: `${origin}/dashboard/billing/fail`,
      });
      // 성공 시 토스가 successUrl 로 리다이렉트하므로 이후 코드는 실행되지 않음
    } catch (e) {
      setErr((e as Error).message ?? "카드 등록을 시작할 수 없습니다.");
      setBusyPlan(null);
    }
  }

  const hasCard = !!sub && sub.status !== "INACTIVE";
  const statusMeta =
    (sub && STATUS_META[sub.status]) ?? STATUS_META.INACTIVE;

  return (
    <div className="space-y-6 max-w-3xl">
      <Script
        src="https://js.tosspayments.com/v1/payment"
        strategy="afterInteractive"
        onLoad={() => setSdkReady(true)}
        onReady={() => setSdkReady(true)}
      />

      <div>
        <h1 className="text-[20px] font-bold tracking-tight text-gray-900">
          결제 / 구독
        </h1>
        <p className="text-[13px] text-gray-500 mt-0.5">
          토스페이먼츠 카드 자동결제로 매월 구독료가 청구됩니다.
        </p>
      </div>

      {err && (
        <Card className="p-4 border-red-200 bg-red-50">
          <p className="text-[13px] text-red-700">{err}</p>
        </Card>
      )}

      {/* 현재 구독 상태 */}
      <Card className="p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-gray-900">
            현재 구독
          </h2>
          <Badge tone={statusMeta.tone}>{statusMeta.label}</Badge>
        </div>

        {isLoading || !sub ? (
          <p className="text-[13px] text-gray-400">불러오는 중...</p>
        ) : (
          <div className="grid grid-cols-2 gap-y-3 gap-x-4 text-[13px]">
            <div className="text-gray-500">플랜</div>
            <div className="text-gray-900 font-medium">
              {sub.plan_label}
              {sub.amount > 0 && (
                <span className="text-gray-500 font-normal">
                  {" "}
                  · {won(sub.amount)}/월
                </span>
              )}
            </div>

            <div className="text-gray-500">결제수단</div>
            <div className="text-gray-900">
              {hasCard && sub.card_number_masked
                ? `${sub.card_company ?? "카드"} ${sub.card_number_masked}`
                : "미등록"}
            </div>

            <div className="text-gray-500">다음 결제일</div>
            <div className="text-gray-900">
              {sub.next_billing_date ?? "—"}
            </div>

            {sub.canceled_at && (
              <>
                <div className="text-gray-500">해지일</div>
                <div className="text-gray-900">
                  {sub.canceled_at.slice(0, 10)}
                </div>
              </>
            )}
          </div>
        )}

        {sub && sub.status === "PAST_DUE" && (
          <div className="flex items-center justify-between rounded-lg bg-red-50 border border-red-200 p-3">
            <p className="text-[12px] text-red-700">
              마지막 결제가 실패했습니다. 카드 한도·유효기간을 확인 후
              재시도해주세요.
            </p>
            <Button
              variant="danger"
              onClick={() => retry.mutate()}
              disabled={retry.isPending}
            >
              {retry.isPending ? "결제 중..." : "결제 재시도"}
            </Button>
          </div>
        )}

        {sub &&
          (sub.status === "ACTIVE" || sub.status === "PAST_DUE") && (
            <div className="flex justify-end">
              <Button
                variant="ghost"
                onClick={() => {
                  if (
                    window.confirm(
                      "구독을 해지하시겠습니까? 다음 결제일부터 청구가 중단됩니다.",
                    )
                  )
                    cancelSub.mutate();
                }}
                disabled={cancelSub.isPending}
              >
                구독 해지
              </Button>
            </div>
          )}
      </Card>

      {/* 플랜 선택 / 변경 */}
      <Card className="p-5 space-y-4">
        <h2 className="text-[14px] font-semibold text-gray-900">
          {hasCard ? "플랜 변경" : "플랜 선택 후 카드 등록"}
        </h2>
        {!sdkReady && !hasCard && (
          <p className="text-[12px] text-gray-400">결제 모듈 로딩 중...</p>
        )}
        <div className="grid sm:grid-cols-3 gap-3">
          {(plans ?? []).map((p) => {
            const current = sub?.plan === p.code && hasCard;
            return (
              <div
                key={p.code}
                className={
                  "rounded-xl border p-4 flex flex-col gap-2 " +
                  (current
                    ? "border-gray-900 bg-gray-50"
                    : "border-gray-200")
                }
              >
                <div className="flex items-center justify-between">
                  <span className="text-[14px] font-bold text-gray-900">
                    {p.label}
                  </span>
                  {current && <Badge tone="success">현재</Badge>}
                </div>
                <div className="text-[18px] font-bold text-gray-900">
                  {won(p.amount)}
                  <span className="text-[12px] font-normal text-gray-500">
                    {" "}
                    / 월
                  </span>
                </div>
                <div className="text-[12px] text-gray-500">
                  거래처 {p.clients_limit} · {p.phase}
                </div>
                {hasCard ? (
                  <Button
                    variant={current ? "secondary" : "primary"}
                    disabled={current || changePlan.isPending}
                    onClick={() => changePlan.mutate(p.code)}
                  >
                    {current
                      ? "이용중"
                      : changePlan.isPending
                        ? "변경 중..."
                        : "이 플랜으로 변경"}
                  </Button>
                ) : (
                  <Button
                    disabled={!sdkReady || busyPlan === p.code}
                    onClick={() => registerCard(p.code)}
                  >
                    {busyPlan === p.code
                      ? "이동 중..."
                      : "카드 등록하고 시작"}
                  </Button>
                )}
              </div>
            );
          })}
        </div>
        {hasCard && (
          <p className="text-[11px] text-gray-400">
            플랜 변경 시 다음 결제일부터 새 금액이 적용됩니다 (일할 정산 없음).
          </p>
        )}
      </Card>

      {/* 결제 이력 */}
      <Card className="p-5 space-y-3">
        <h2 className="text-[14px] font-semibold text-gray-900">결제 이력</h2>
        {!payments || payments.length === 0 ? (
          <p className="text-[13px] text-gray-400">결제 이력이 없습니다.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-200">
                  <th className="py-2 font-medium">청구월</th>
                  <th className="py-2 font-medium">내역</th>
                  <th className="py-2 font-medium text-right">금액</th>
                  <th className="py-2 font-medium text-center">상태</th>
                  <th className="py-2 font-medium">일시</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((pm) => (
                  <tr
                    key={pm.id}
                    className="border-b border-gray-100 last:border-0"
                  >
                    <td className="py-2 text-gray-700">
                      {pm.billing_period}
                    </td>
                    <td className="py-2 text-gray-700">{pm.order_name}</td>
                    <td className="py-2 text-right text-gray-900">
                      {won(pm.amount)}
                    </td>
                    <td className="py-2 text-center">
                      {pm.status === "PAID" ? (
                        <Badge tone="success">완료</Badge>
                      ) : pm.status === "FAILED" ? (
                        <Badge tone="danger">실패</Badge>
                      ) : (
                        <Badge tone="neutral">대기</Badge>
                      )}
                    </td>
                    <td className="py-2 text-gray-500">
                      {(pm.approved_at ?? pm.created_at).slice(0, 16).replace("T", " ")}
                      {pm.status === "FAILED" && pm.failure_message && (
                        <span className="block text-[11px] text-red-500">
                          {pm.failure_message}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
