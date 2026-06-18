import fs from "node:fs/promises";
import path from "node:path";

/* ============================================================
   블로그 글 메타데이터 — @next/mdx는 YAML frontmatter를 지원하지 않으므로
   각 .mdx 파일이 `export const metadata = {...}`를 내보낸다.
   서버 전용 (fs 사용) — Server Component에서만 호출.
   ============================================================ */

export type PostMeta = {
  title: string;
  date: string; // ISO yyyy-mm-dd
  summary: string;
  author?: string;
};

export type PostListItem = PostMeta & { slug: string };

const BLOG_DIR = path.join(process.cwd(), "src/content/blog");

export async function getPostSlugs(): Promise<string[]> {
  const files = await fs.readdir(BLOG_DIR);
  return files
    .filter((f) => f.endsWith(".mdx"))
    .map((f) => f.replace(/\.mdx$/, ""));
}

export async function getPostMeta(slug: string): Promise<PostMeta> {
  const mod = await import(`@/content/blog/${slug}.mdx`);
  return mod.metadata as PostMeta;
}

export async function getAllPosts(): Promise<PostListItem[]> {
  const slugs = await getPostSlugs();
  const posts = await Promise.all(
    slugs.map(async (slug) => ({ slug, ...(await getPostMeta(slug)) })),
  );
  // 최신순 정렬
  return posts.sort((a, b) => (a.date < b.date ? 1 : -1));
}
