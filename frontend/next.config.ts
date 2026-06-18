import type { NextConfig } from "next";
import createMDX from "@next/mdx";

const nextConfig: NextConfig = {
  // .md/.mdx 파일을 라우트/임포트로 처리할 수 있도록 허용
  pageExtensions: ["js", "jsx", "md", "mdx", "ts", "tsx"],
};

// 플러그인 없이 기본 MDX 컴파일 — Turbopack과 호환
const withMDX = createMDX({});

export default withMDX(nextConfig);
