// 로그인 시 선택하는 "데모버전 / 이지원 버전" 모드 (plan/16-wehago-rpa.md §3-6).
// 영구 저장하지 않는다 — 매 로그인마다 새로 선택하며, sessionStorage에는 로그인 직후부터
// 이번 탭 세션 동안 배너 표시용으로만 들고 있는다.

export type LoginMode = "demo" | "agent";

const KEY = "taxflow.loginMode";

export function setLoginMode(mode: LoginMode) {
  try {
    sessionStorage.setItem(KEY, mode);
  } catch {
    // 프라이빗 브라우징 등 sessionStorage 사용 불가 환경은 조용히 무시한다.
  }
}

export function getLoginMode(): LoginMode {
  try {
    return sessionStorage.getItem(KEY) === "agent" ? "agent" : "demo";
  } catch {
    return "demo";
  }
}
