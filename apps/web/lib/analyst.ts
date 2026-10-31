"use client";
// Analyst identity for development (master prompt rule 12: real login arrives at Stage 8).
// Sent as X-Ergplan-Actor / X-Ergplan-Role headers on every write through the /api proxy.
const KEY = "ergplan-analyst";

export function getAnalyst(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function setAnalyst(email: string): void {
  try {
    localStorage.setItem(KEY, email);
  } catch {
    /* storage may be unavailable */
  }
}

export async function analystFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const actor = getAnalyst();
  const r = await fetch(`/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(actor ? { "X-Ergplan-Actor": actor, "X-Ergplan-Role": "analyst" } : {}),
      ...(init.headers ?? {}),
    },
  });
  const text = await r.text();
  const body = text ? JSON.parse(text) : null;
  if (!r.ok) {
    const d = body?.detail;
    throw new Error(typeof d === "string" ? d : d?.message ? `${d.message}: ${JSON.stringify(d.errors)}` : `${r.status}`);
  }
  return body as T;
}
