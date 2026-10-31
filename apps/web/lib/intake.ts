// Client journey steps 1 and 4: bills, confirmations, the site intake and its load profile.
// Calls go through the same-origin /api proxy. Identity until Stage 8 is a dev header (rule 12).

export type RefKind = "regulation" | "order" | "client_stated" | "assumption" | "measured" | "derived" | "bill";

export type Ref = {
  kind: RefKind;
  document_id?: string;
  page?: number;
  quote?: string;
  note?: string;
  bill_id?: string;
  field_path?: string;
  url?: string;
};

export type Fact<T> = { value: T; provenance: "bill" | "client_stated" | "assumption"; ref?: Ref | null };

export type TodEnergy = { start: string; end: string; energy: Fact<string>; slot?: string | null };

export type MonthFacts = {
  month: string;
  energy: Fact<string>;
  energy_unit: "kWh" | "kVAh";
  tod: TodEnergy[];
  max_kva?: Fact<string> | null;
  power_factor?: Fact<string> | null;
  bill_inr?: Fact<string> | null;
  bill_id?: string | null;
  shutdown_days: number[];
  unmapped_tod_slots: string[];
};

export type AssetIn = { kind: string; params: Record<string, unknown>; provenance?: Fact<unknown>["provenance"] };

export type SiteIntake = {
  client_name: Fact<string>;
  site_name: Fact<string>;
  state: Fact<string>;
  discom: Fact<string>;
  category: Fact<string>;
  voltage_kv: Fact<string>;
  contract_demand_kva: Fact<string>;
  consumer_number?: Fact<string> | null;
  rate_block?: Fact<string> | null;
  industry_shape: Fact<string>;
  weekly_off: Fact<number[]>;
  land_acres?: Fact<string> | null;
  roof_sqm?: Fact<string> | null;
  months: MonthFacts[];
  assets: AssetIn[];
};

export type FieldReview = {
  path: string;
  value: string | null;
  unit: string | null;
  verification: string | null;
  page: number | null;
  required: boolean;
  confirmed: boolean;
  needs_confirmation: boolean;
};

export type BillOut = {
  id: string;
  filename: string | null;
  bill_month: string | null;
  status: string;
  accepted: boolean;
  accepted_by: string | null;
  discom: string | null;
  connection_id: string | null;
  review_reasons: string[];
  fields: FieldReview[];
  outstanding: string[];
  tod_slots: (string | null)[];
  file_url: string;
};

export type SourcedValue = { value: string; unit: string; source_refs: Ref[]; label?: string | null };

export type ProfileOut = {
  id: string;
  connection_id: string;
  version: number;
  provenance: string;
  year_start: string;
  blocks: number;
  method: Record<string, unknown>;
  months: { month: string; energy_kwh: SourcedValue; max_kw: SourcedValue; extrapolated: boolean; peak_shortfall_kw: string | null }[];
  week_kw: string[];
};

export type ConnectionOut = {
  id: string;
  client: { id: string; name: string };
  site: { id: string; name: string; state: string; industry_shape: string; weekly_off: number[] };
  discom_id: string;
  tariff_category: string | null;
  voltage_kv: string | null;
  contract_demand_kva: string | null;
  connection_kind: string;
  bills: { id: string; bill_month: string | null; status: string; accepted: boolean }[];
  profiles: { id: string; version: number; provenance: string }[];
};

export type ShapeOut = { id: string; name: string; note: string | null; working_days: number[] };

export const FIELD_LABEL: Record<string, string> = {
  "period.bill_month": "Bill month",
  "energy.kwh": "Energy (kWh)",
  "energy.kvah": "Energy (kVAh)",
  "energy.billed_units": "Billed units",
  "demand.max_kva": "Recorded maximum demand",
  "demand.contract_kva": "Contract demand",
  "tariff.category": "Tariff category",
  "energy.power_factor": "Power factor",
  "totals.current_charges": "Current charges (₹)",
  "consumer.account_number": "Consumer number",
  "consumer.name": "Consumer name",
  "utility.name": "DISCOM",
};

export function fieldLabel(path: string, slots: (string | null)[] = []): string {
  const m = path.match(/^energy\.tod\.(\d+)\.kwh$/);
  if (m) return `ToD energy · ${slots[Number(m[1])] ?? `slot ${Number(m[1]) + 1}`}`;
  return FIELD_LABEL[path] ?? path;
}

export const DISCOMS: { id: string; state: string; name: string }[] = [
  { id: "npcl", state: "UP", name: "Noida Power Company (NPCL)" },
  { id: "pvvnl", state: "UP", name: "Paschimanchal (PVVNL)" },
  { id: "mvvnl", state: "UP", name: "Madhyanchal (MVVNL)" },
  { id: "puvvnl", state: "UP", name: "Purvanchal (PuVVNL)" },
  { id: "dvvnl", state: "UP", name: "Dakshinanchal (DVVNL)" },
  { id: "kesco", state: "UP", name: "KESCO" },
  { id: "msedcl", state: "MH", name: "MSEDCL (Mahavitaran)" },
];

export const CATEGORIES: Record<string, string[]> = { UP: ["HV-2", "HV-1", "LMV-6"], MH: ["HT I(A)", "HT II", "HT I(B)", "LT V"] };

export const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const CLIENT_KEY = "ergplan-client";

export function getClientEmail(): string {
  try {
    return localStorage.getItem(CLIENT_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setClientEmail(v: string): void {
  try {
    localStorage.setItem(CLIENT_KEY, v);
  } catch {
    /* storage may be unavailable */
  }
}

export async function clientFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const who = getClientEmail();
  const headers: Record<string, string> = { ...(who ? { "X-Ergplan-Actor": who, "X-Ergplan-Role": "client" } : {}) };
  if (!(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const r = await fetch(`/api${path}`, { ...init, headers: { ...headers, ...((init.headers as Record<string, string>) ?? {}) } });
  const text = await r.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!r.ok) throw new Error(errorText(r.status, body));
  return body as T;
}

export function errorText(status: number, body: unknown): string {
  const d = (body as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e: { msg?: string; loc?: unknown[] }) => `${(e.loc ?? []).slice(1).join(".")}: ${e.msg}`).join("; ");
  if (d && typeof d === "object" && "message" in d) return String((d as { message: string }).message);
  return `Request failed (${status})`;
}

export function stated<T>(value: T): Fact<T> {
  return { value, provenance: "client_stated" };
}

export function monthLabel(iso: string): string {
  const [y, m] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleString("en-IN", { month: "short", year: "numeric", timeZone: "UTC" });
}

export function refHref(ref: Ref | null | undefined): string | null {
  if (!ref) return null;
  // the API's SourceRef.url is the path behind the same-origin /api proxy
  if (ref.kind === "bill" && ref.bill_id) return `/api${ref.url ?? `/bills/${ref.bill_id}/file`}`;
  // invariant 1: a document ref opens the stored PDF at its page (/documents/{id}#page=N, through the /api proxy)
  if (ref.document_id && ref.page) return `/api/documents/${ref.document_id}#page=${ref.page}`;
  return null;
}

export const PROVENANCE_LABEL: Record<string, string> = { bill: "from your bill", client_stated: "you said", assumption: "assumed", measured: "meter data" };
