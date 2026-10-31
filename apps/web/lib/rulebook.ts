// Shapes returned by /rulebooks and helpers to read rule rows.
export type SourceRef = {
  kind: string;
  document_id?: string;
  page?: number;
  printed_page?: string;
  quote?: string;
  effective_from?: string;
  note?: string;
};

export type Version = {
  id: string;
  family: string;
  jurisdiction_id: string;
  version: number;
  status: "draft" | "approved" | "superseded" | "rejected";
  title: string | null;
  effective_from: string;
  effective_to: string | null;
  origin: string;
  golden_status: string;
  created_by: string;
  approved_by: string | null;
  notes: string | null;
  rows: number;
};

export type Row = {
  id: string;
  position: number;
  label: string | null;
  scope: Record<string, unknown>;
  body: Record<string, unknown>;
  source_ref: SourceRef;
  field_refs: Record<string, SourceRef>;
  review: Record<string, unknown>;
};

export type Golden = {
  name: string;
  passed: boolean | null;
  given: Record<string, unknown>;
  expect: Record<string, unknown>;
  actual: Record<string, unknown> | null;
};

export type VersionDetail = { version: Version; rows: Row[]; golden: Golden[] };

export type Leaf = { pointer: string; value: unknown };

/** Every scalar in a body as a JSON pointer and its value, in order. */
export function leaves(node: unknown, base = ""): Leaf[] {
  if (node === null || typeof node !== "object") return [{ pointer: base || "/", value: node }];
  const out: Leaf[] = [];
  const entries = Array.isArray(node) ? node.map((v, i) => [String(i), v] as const) : Object.entries(node as object);
  for (const [k, v] of entries) out.push(...leaves(v, `${base}/${k}`));
  return out;
}

/** Schema description for a JSON pointer inside a family's body schema. */
export function describe(schema: Record<string, unknown> | undefined, pointer: string): string {
  let node: Record<string, unknown> | undefined = schema;
  for (const part of pointer.split("/").filter(Boolean)) {
    if (!node) return "";
    const props = node.properties as Record<string, Record<string, unknown>> | undefined;
    const items = node.items as Record<string, unknown> | undefined;
    const addl = node.additionalProperties as Record<string, unknown> | undefined;
    node = props?.[part] ?? (/^\d+$/.test(part) ? items : undefined) ?? (typeof addl === "object" ? addl : undefined);
  }
  return (node?.description as string) ?? "";
}

/** Set a value at a JSON pointer, returning a new object. */
export function setAt<T>(obj: T, pointer: string, value: unknown): T {
  const copy = structuredClone(obj) as unknown as Record<string, unknown>;
  const parts = pointer.split("/").filter(Boolean);
  let node: Record<string, unknown> = copy;
  parts.slice(0, -1).forEach((p) => (node = node[p] as Record<string, unknown>));
  node[parts[parts.length - 1]] = value;
  return copy as unknown as T;
}

export const FAMILY_LABEL: Record<string, string> = {
  tariff_schedule: "Tariff schedule",
  tod_slots: "Time of day",
  oa_charge: "Open-access charges",
  settlement: "Settlement and banking",
  regulatory_limit: "Regulatory limits",
  ists_waiver: "ISTS waiver",
  net_metering: "Net metering",
};

export function scopeChips(scope: Record<string, unknown>): string[] {
  const out: string[] = [];
  for (const [k, v] of Object.entries(scope)) {
    if (k === "voltage_kv" || k === "capacity_mw" || k === "contract_demand_kva" || k === "load_kw") {
      const b = v as { min?: number; max?: number; min_exclusive?: boolean; max_exclusive?: boolean };
      const unit = k === "voltage_kv" ? "kV" : k === "capacity_mw" ? "MW" : k === "load_kw" ? "kW" : "kVA";
      const lo = b.min !== undefined ? `${b.min_exclusive ? ">" : "≥"} ${b.min}` : "";
      const hi = b.max !== undefined ? `${b.max_exclusive ? "<" : "≤"} ${b.max}` : "";
      out.push(b.min !== undefined && b.min === b.max ? `${b.min} ${unit}` : `${[lo, hi].filter(Boolean).join(" and ")} ${unit}`);
    } else if (k === "months") {
      const m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      out.push((v as number[]).map((x) => m[x - 1]).join(" "));
    } else if (Array.isArray(v)) out.push(`${k.replaceAll("_", " ")}: ${v.join(", ")}`);
    else out.push(`${k.replaceAll("_", " ")}: ${String(v)}`);
  }
  return out;
}
