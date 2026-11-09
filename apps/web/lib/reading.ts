// The reading view of one bill (GET /bills/{id}/reading) and the hand-off to planning
// (GET /bills/{id}/plan-inputs). Every figure carries a bill source_ref (invariant 1).
import type { BillOut, Ref } from "@/lib/intake";

export type Box = { x: string; y: string; w: string; h: string };

export type ReaderReading = {
  reader: string;
  reader_name: string;
  printed: string | null;
  value: string | null;
  page: number | null;
  box: Box | null;
};

export type ReadValue = {
  path: string;
  label: string;
  value: string | null;
  unit: string | null;
  printed: string | null;
  page: number | null;
  box: Box | null;
  verification: string | null;
  readers: string[];
  readings: ReaderReading[];
  source_ref: Ref | null;
  needs_confirmation: boolean;
  confirmed: boolean;
  confirmable: boolean;
};

export type TodRow = {
  slot: string;
  start: string | null;
  end: string | null;
  unit: string;
  consumption: ReadValue | null;
  open_access: ReadValue | null;
  net: ReadValue | null;
};

export type ChargeRow = {
  label: string;
  code: string | null;
  group: string | null;
  kind: string | null;
  stage: string | null;
  tod_slot: string | null;
  quantity: string | null;
  rate: string | null;
  amount: ReadValue;
  recheck: string | null;
};

export type CheckRow = { id: string; description: string | null; status: string; expected: string | null; actual: string | null };

export type BillReading = {
  bill_id: string;
  filename: string | null;
  file_url: string;
  pages: number[];
  page_url: string;
  status: string;
  accepted: boolean;
  discom: string | null;
  profile_status: string | null;
  readers_used: string[];
  fields: ReadValue[];
  tod: TodRow[];
  charges: ChargeRow[];
  checks: CheckRow[];
  review_reasons: string[];
  outstanding: string[];
  cost_usd: string | null;
};

export type Sourced = { value: string; unit: string; source_refs: Ref[]; label?: string | null };
export type PlanValue = { key: string; label: string; value: Sourced; verification: string | null };
export type PlanSlot = {
  slot: string;
  start: string | null;
  end: string | null;
  consumption: PlanValue | null;
  open_access: PlanValue | null;
  billed: PlanValue | null;
  rate: PlanValue | null;
  share_of_consumption: PlanValue | null;
};
export type PlanInputs = {
  bill_id: string;
  bill_month: string | null;
  discom: string | null;
  tariff_category: string | null;
  category_code: string | null;
  category_note: string | null;
  accepted: boolean;
  energy_unit: string;
  facts: PlanValue[];
  slots: PlanSlot[];
  derived: PlanValue[];
  notes: string[];
  recognition: Recognition;
};

// What the bill says about the connection: its DISCOM and state, the open access it already takes
// (each finding links to its bill page), and the state settlement rules the next stage applies.
export type Evidence = { finding: string; ref: Ref };
export type SettlementRoute = {
  ownership: string;
  ownership_label: string;
  rule_label: string | null;
  rulebook: string | null;
  version: number | null;
  ref: Ref | null;
};
export type Recognition = {
  discom: string | null;
  discom_name: string | null;
  discom_how: string | null;
  discom_ref: Ref | null;
  state: string | null;
  state_name: string | null;
  open_access: "none_seen" | "open_access" | "green_tariff";
  open_access_kinds: string[];
  evidence: Evidence[];
  settlement: SettlementRoute[];
  notes: string[];
};

export const OPEN_ACCESS_LABEL: Record<Recognition["open_access"], string> = {
  none_seen: "No open access on this bill",
  open_access: "Open access",
  green_tariff: "Green tariff",
};
export const KIND_LABEL: Record<string, string> = {
  captive: "captive",
  group_captive: "group captive",
  third_party: "third party",
  exchange: "power exchange",
  geoa: "GEOA",
};

export const READERS: { id: string; name: string; what: string }[] = [
  { id: "text_layer", name: "PDF text", what: "the PDF's own text, where it has one" },
  { id: "local_ocr", name: "Local OCR", what: "characters read on the server" },
  { id: "docling", name: "Docling", what: "page layout and table cells" },
  { id: "model_a", name: "Model A", what: "an OpenAI vision model" },
  { id: "llamaparse", name: "LlamaParse", what: "LlamaIndex's document reader" },
  { id: "model_b", name: "Model B", what: "a second vision model" },
];

export const VERIFICATION: Record<string, string> = {
  verified: "Two independent readers agree",
  confirmed: "Confirmed by you",
  disputed: "Readers disagree: please check",
  unverified: "Read once: please check",
};

/** Indian digit grouping for a figure as text (no float arithmetic). */
export function indian(v: string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const m = /^(-?)(\d+)(\.\d+)?$/.exec(v.replace(/,/g, ""));
  if (!m) return v;
  const [, sign, int, frac = ""] = m;
  if (int.length <= 3) return `${sign}${int}${frac}`;
  const head = int.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return `${sign}${head},${int.slice(-3)}${frac}`;
}

export function pct(b: Box | null, key: keyof Box): string {
  return b ? `${(Number(b[key]) * 100).toFixed(3)}%` : "0";
}

export type BillReadOut = {
  id: string;
  filename: string | null;
  pages: number;
  page_url: string;
  status: "queued" | "reading" | "done" | "failed";
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  bills: BillOut[];
};

export type SearchHit = {
  bill_id: string;
  bill_month: string | null;
  discom: string | null;
  consumer: string | null;
  account: string | null;
  filename: string | null;
  status: string;
  score: number;
  lines: string[];
  reading_url: string;
};
export type SearchOut = { query: string; searched: number; hits: SearchHit[] };
export type MonthSlot = { slot: string; consumption: Sourced | null; open_access: Sourced | null; billed: Sourced | null };
export type MonthRow = {
  bill_id: string;
  month: string;
  verified: boolean;
  unit: string;
  consumption: Sourced | null;
  open_access: Sourced | null;
  open_access_share: Sourced | null;
  billed: Sourced | null;
  max_kva: Sourced | null;
  contract_kva: Sourced | null;
  power_factor: Sourced | null;
  energy_charges: Sourced | null;
  current_charges: Sourced | null;
  net_payable: Sourced | null;
  slots: MonthSlot[];
};
export type AccountSeries = { account: string | null; consumer: string | null; discom: string | null; months: MonthRow[] };
