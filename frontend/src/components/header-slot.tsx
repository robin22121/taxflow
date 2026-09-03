"use client";

import { createContext, useContext } from "react";

/**
 * 대시보드 상단 헤더의 페이지별 삽입 지점.
 * 레이아웃이 DOM 노드를 제공하고, 각 페이지가 createPortal로 내용을 채운다.
 */
export type HeaderSlots = {
  /** 로고 오른쪽 — 페이지 제목·마감일 등 */
  info: HTMLElement | null;
  /** 사용자 메뉴 왼쪽 — 페이지 액션 버튼 */
  actions: HTMLElement | null;
};

export const HeaderSlotContext = createContext<HeaderSlots>({
  info: null,
  actions: null,
});

export function useHeaderSlots() {
  return useContext(HeaderSlotContext);
}
