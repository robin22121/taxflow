import type { MDXComponents } from "mdx/types";

/* ============================================================
   MDX 전역 컴포넌트 — @next/mdx App Router 필수 파일.
   @tailwindcss/typography 없이 블로그 본문 스타일을 직접 매핑.
   디자인 토큰: gray-900 본문 · blue-600 액센트 · Pretendard
   ============================================================ */

const components: MDXComponents = {
  h1: ({ children }) => (
    <h1 className="mt-10 mb-4 text-[28px] font-extrabold tracking-tight text-gray-900 sm:text-[34px]">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mt-10 mb-3 text-[22px] font-bold tracking-tight text-gray-900 sm:text-[26px]">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mt-8 mb-2 text-[18px] font-semibold tracking-tight text-gray-900">
      {children}
    </h3>
  ),
  p: ({ children }) => (
    <p className="my-4 text-[15.5px] leading-[1.8] text-gray-700">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="my-4 list-disc space-y-2 pl-5 text-[15.5px] leading-[1.8] text-gray-700">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="my-4 list-decimal space-y-2 pl-5 text-[15.5px] leading-[1.8] text-gray-700">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="pl-1">{children}</li>,
  a: ({ children, href }) => (
    <a
      href={href}
      className="font-medium text-blue-600 underline underline-offset-2 hover:text-blue-700"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-6 border-l-4 border-blue-600/30 bg-gray-50 py-2 pl-4 text-[15px] italic text-gray-600">
      {children}
    </blockquote>
  ),
  code: ({ children }) => (
    <code className="rounded bg-gray-100 px-1.5 py-0.5 text-[13.5px] text-gray-800">
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <pre className="my-6 overflow-x-auto rounded-[14px] border border-gray-200 bg-gray-900 p-4 text-[13px] leading-relaxed text-gray-100">
      {children}
    </pre>
  ),
  hr: () => <hr className="my-10 border-gray-200" />,
  table: ({ children }) => (
    <div className="my-6 overflow-x-auto">
      <table className="w-full border-collapse text-[14px]">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-b border-gray-300 px-3 py-2 text-left font-semibold text-gray-900">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-b border-gray-100 px-3 py-2 text-gray-700">{children}</td>
  ),
};

export function useMDXComponents(): MDXComponents {
  return components;
}
