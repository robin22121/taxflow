import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getPostMeta, getPostSlugs } from "@/lib/blog";

type Params = { slug: string };

// 정의되지 않은 slug 접근 시 404
export const dynamicParams = false;

export async function generateStaticParams(): Promise<Params[]> {
  const slugs = await getPostSlugs();
  return slugs.map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { slug } = await params;
  try {
    const meta = await getPostMeta(slug);
    return {
      title: `${meta.title} — 이지원천 블로그`,
      description: meta.summary,
    };
  } catch {
    return {};
  }
}

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${y}년 ${Number(m)}월 ${Number(d)}일`;
}

export default async function BlogPostPage({
  params,
}: {
  params: Promise<Params>;
}) {
  const { slug } = await params;

  let Post: React.ComponentType;
  let meta;
  try {
    const mod = await import(`@/content/blog/${slug}.mdx`);
    Post = mod.default;
    meta = mod.metadata as { title: string; date: string; author?: string };
  } catch {
    notFound();
  }

  return (
    <div className="bg-white text-gray-900">
      <header className="sticky top-0 z-50 border-b border-gray-200/70 bg-white/80 backdrop-blur-md">
        <nav className="mx-auto flex h-16 max-w-2xl items-center justify-between px-5">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-gray-900 text-[15px] font-extrabold text-white">
              이
            </span>
            <span className="text-[17px] font-bold tracking-tight text-gray-900">
              이지원천
            </span>
          </Link>
          <Link
            href="/blog"
            className="text-[13px] font-medium text-gray-600 transition-colors hover:text-gray-900"
          >
            ← 블로그 목록
          </Link>
        </nav>
      </header>

      <article className="mx-auto max-w-2xl px-5 py-16 sm:py-20">
        <div className="mb-8 border-b border-gray-100 pb-8">
          <time className="t-num text-[13px] font-medium text-blue-600">
            {formatDate(meta.date)}
          </time>
          {meta.author && (
            <span className="ml-3 text-[13px] text-gray-400">· {meta.author}</span>
          )}
        </div>
        <Post />

        <div className="mt-16 rounded-[20px] border border-blue-600/20 bg-blue-600/[0.04] p-8 text-center">
          <h3 className="text-[18px] font-bold text-gray-900">
            원천세 업무, 이지원천으로 시작하세요
          </h3>
          <p className="mt-2 text-[14px] text-gray-600">
            지금 베타 신청하면 최대 18개월 혜택을 받을 수 있습니다.
          </p>
          <Link
            href="/#beta"
            className="mt-5 inline-flex items-center justify-center rounded-full border border-blue-600 bg-blue-600 px-6 py-2.5 text-[13.5px] font-semibold text-white transition-all hover:brightness-110"
          >
            베타 신청하기 →
          </Link>
        </div>
      </article>
    </div>
  );
}
