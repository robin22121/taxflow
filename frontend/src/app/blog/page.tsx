import type { Metadata } from "next";
import Link from "next/link";

import { getAllPosts } from "@/lib/blog";

export const metadata: Metadata = {
  title: "블로그 — 이지원천",
  description:
    "원천세·급여·4대보험 실무와 세무사무소 자동화에 대한 이지원천의 이야기.",
};

function formatDate(iso: string): string {
  // ISO yyyy-mm-dd → yyyy년 m월 d일
  const [y, m, d] = iso.split("-");
  return `${y}년 ${Number(m)}월 ${Number(d)}일`;
}

export default async function BlogIndexPage() {
  const posts = await getAllPosts();

  return (
    <div className="bg-white text-gray-900">
      <header className="sticky top-0 z-50 border-b border-gray-200/70 bg-white/80 backdrop-blur-md">
        <nav className="mx-auto flex h-16 max-w-3xl items-center justify-between px-5">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-gray-900 text-[15px] font-extrabold text-white">
              이
            </span>
            <span className="text-[17px] font-bold tracking-tight text-gray-900">
              이지원천
            </span>
          </Link>
          <Link
            href="/"
            className="text-[13px] font-medium text-gray-600 transition-colors hover:text-gray-900"
          >
            ← 홈으로
          </Link>
        </nav>
      </header>

      <main className="mx-auto max-w-3xl px-5 py-16 sm:py-24">
        <div className="mb-12">
          <span className="inline-flex items-center rounded-full bg-blue-600/8 px-2.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-widest text-blue-600">
            블로그
          </span>
          <h1 className="mt-4 text-[32px] font-extrabold tracking-tight text-gray-900 sm:text-[40px]">
            원천세 실무 이야기
          </h1>
          <p className="mt-3 text-[15px] leading-relaxed text-gray-500">
            급여·4대보험·급여명세서 실무와 세무사무소 자동화에 대한 인사이트.
          </p>
        </div>

        {posts.length === 0 ? (
          <p className="text-[14px] text-gray-400">아직 게시된 글이 없습니다.</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {posts.map((post) => (
              <li key={post.slug}>
                <Link
                  href={`/blog/${post.slug}`}
                  className="group block py-7 transition-colors"
                >
                  <time className="t-num text-[12.5px] font-medium text-gray-400">
                    {formatDate(post.date)}
                  </time>
                  <h2 className="mt-2 text-[20px] font-bold tracking-tight text-gray-900 transition-colors group-hover:text-blue-600">
                    {post.title}
                  </h2>
                  <p className="mt-2 text-[14.5px] leading-relaxed text-gray-500">
                    {post.summary}
                  </p>
                  <span className="mt-3 inline-flex items-center gap-1 text-[13px] font-medium text-blue-600">
                    읽어보기 →
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
