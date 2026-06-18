"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { clearTokens, getToken } from "@/lib/api";

/**
 * 로그인된 사용자가 랜딩(홈)에 접속하면 대시보드로 보낸다.
 * 마케팅 페이지는 서버 컴포넌트로 정적 렌더링하고, 이 작은
 * 클라이언트 아일랜드만 토큰을 확인한다. 비로그인 방문자에게는
 * 아무 영향이 없다.
 *
 * 만료된 토큰이 localStorage에 남아 있으면 대시보드로 보냈다가
 * 백엔드가 401을 돌려주는 사이클이 생긴다. exp claim을 미리
 * 파싱해서 만료된 경우엔 토큰을 정리하고 랜딩을 그대로 보여준다.
 */
export function AuthRedirect() {
  const router = useRouter();
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    try {
      const payload = token.split(".")[1];
      const json = JSON.parse(
        atob(payload.replace(/-/g, "+").replace(/_/g, "/")),
      );
      if (typeof json.exp === "number" && json.exp * 1000 > Date.now()) {
        router.replace("/dashboard");
      } else {
        clearTokens();
      }
    } catch {
      clearTokens();
    }
  }, [router]);
  return null;
}
