import type { Ref, SourcedValue } from "./intake";

export type TariffLine = { code: string; label: string; slot: string | null; amount: SourcedValue; quantity: SourcedValue | null; rate: SourcedValue | null };
export type ReplayLine = {
  group: string; label: string; billed: string | null; computed: SourcedValue | null; difference: string;
  status: "match" | "explained" | "unexplained" | "not_billed"; explanation: string; gap: string | null; billed_items: string[];
};
export type ReplayOut = {
  bill_id: string; bill_month: string | null; evaluated_on: string; status: string; schedule: string | null; tod: string | null;
  computed_total: SourcedValue | null; billed_total: string | null; total_difference: string; lines: ReplayLine[];
  tariff_lines: TariffLine[]; gaps: Record<string, string>; notes: string[]; file_url: string;
};
export type RateCard = { month: string; slot: string | null; components: SourcedValue[]; kvah_factor: SourcedValue | null; rate: SourcedValue };
export type AvoidedOut = {
  connection_id: string; profile_version: number; profile_provenance: string; year_start: string; tariff_as_of: string;
  matrix: string[][]; cards: RateCard[]; annual: SourcedValue[]; gaps: Record<string, string>; notes: string[];
};

export function inr(v: string | number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  return `₹${n.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

// Unique refs across values, documents first.
export function uniqueRefs(values: (SourcedValue | null | undefined)[]): Ref[] {
  const seen = new Set<string>();
  const out: Ref[] = [];
  for (const v of values) {
    for (const r of v?.source_refs ?? []) {
      const key = `${r.kind}|${r.document_id ?? ""}|${r.page ?? ""}|${r.bill_id ?? ""}|${r.field_path ?? ""}|${r.note ?? ""}`;
      if (!seen.has(key)) {
        seen.add(key);
        out.push(r);
      }
    }
  }
  const rank = (r: Ref) => (r.kind === "order" || r.kind === "regulation" ? 0 : r.kind === "bill" ? 1 : 2);
  return out.sort((a, b) => rank(a) - rank(b));
}

export function hhmm(block: number): string {
  const m = block * 15;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}
