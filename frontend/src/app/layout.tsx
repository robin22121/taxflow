import type { Metadata } from "next";

import "./globals.css";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "TaxFlow AI",
  description: "세무 업무 AI 자동화 플랫폼",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // suppressHydrationWarning — 브라우저 확장(번역기, Grammarly, 비밀번호 관리자 등)이
  // <html>/<body>에 속성·요소를 주입할 때 발생하는 React #418 hydration 에러를 무시.
  // 한 단계 깊이까지만 적용되므로 앱 내부 컴포넌트는 영향 없음.
  return (
    <html lang="ko" className="h-full antialiased" suppressHydrationWarning>
      <body
        className="min-h-full bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-100"
        suppressHydrationWarning
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
