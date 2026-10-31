// Server-side API access. Types are generated from the API's OpenAPI document (pnpm gen:api → lib/api-types.ts);
// the hand-written shapes here are the subset the pages use until generation runs in CI.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

export type DocumentOut = {
  id: string;
  title: string;
  regulator: string | null;
  jurisdiction: string | null;
  document_kind: string;
  utilities: string[];
  file_sha256: string;
  pages: number;
  order_date: string | null;
  effective_from: string | null;
  url_public: string | null;
  page_hints: Record<string, [number, number] | number[]>;
  notes: string[];
  url: string;
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  if (!r.ok) throw new ApiError(r.status, `${r.status} ${await r.text()}`);
  return (await r.json()) as T;
}

export async function apiOrNull<T>(path: string): Promise<T | null> {
  try {
    return await api<T>(path);
  } catch {
    return null;
  }
}
