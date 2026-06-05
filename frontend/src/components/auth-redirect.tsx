"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { getToken } from "@/lib/api";

/**
 * 로그인된 사용자가 랜딩(홈)에 접속하면 대시보드로 보낸다.
 * 마케팅 페이지는 서버 컴포넌트로 정적 렌더링하고, 이 작은
 * 클라이언트 아일랜드만 토큰을 확인한다. 비로그인 방문자에게는
 * 아무 영향이 없다.
 */
export function AuthRedirect() {
  const router = useRouter();
  useEffect(() => {
    if (getToken()) router.replace("/dashboard");
  }, [router]);
  return null;
}
