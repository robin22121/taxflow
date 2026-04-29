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
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="min-h-full bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-100">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
