"use client";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const TOKEN_KEY = "taxflow_access_token";
const REFRESH_KEY = "taxflow_refresh_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
    body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
    cache: "no-store",
  });

  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
    }
    const message =
      typeof body === "object" && body && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `${res.status} ${res.statusText}`;
    throw new ApiError(res.status, body, message);
  }

  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) return res.json() as Promise<T>;
  return (await res.blob()) as unknown as T;
}

export async function apiUpload<T = unknown>(path: string, file: File): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${BASE}${path}`, { method: "POST", body: fd, headers, cache: "no-store" });
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
    }
    const message =
      typeof body === "object" && body && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `${res.status} ${res.statusText}`;
    throw new ApiError(res.status, body, message);
  }
  return res.json() as Promise<T>;
}

export async function apiBlob(path: string): Promise<Blob> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${BASE}${path}`, { headers, cache: "no-store" });
  if (!res.ok) throw new ApiError(res.status, null, await res.text());
  return res.blob();
}
