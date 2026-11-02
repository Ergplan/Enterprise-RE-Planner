import type { Ref, SourcedValue } from "./intake";

// The audit screen: the chain from the generator's price to the saving (GET /connections/{id}/chain),
// the client's workings set against it, the audit chat and the proposed rule changes.
export type ChainStep = {
  key: string;
  kind: string;
  label: string;
  rate: SourcedValue | null;
  value: SourcedValue;
  running: SourcedValue | null;
  rule_id: string | null;
  pointer: string | null;
  editable: string | null;
};

export type SourceChain = {
  id: string; kind: string; label: string; ownership: string | null; capacity: SourcedValue | null;
  slot: string | null; slots_differ: boolean; landed: ChainStep[]; landed_total: SourcedValue | null;
  energy: ChainStep[]; gaps: Record<string, string>;
};

export type Chain = {
  connection_id: string; site: string; state: string | null; discom: string; scenario_id: string; scenario: string;
  run_id: string; finished_at: string | null; settlement_rule: string | null; settlement_ref: Ref | null;
  sources: SourceChain[]; energy: ChainStep[]; money: ChainStep[]; saving: SourcedValue; notes: string[];
};

export type LineStatus = "open" | "matches" | "differs" | "unmatched" | "ours_accepted" | "stated" | "proposed" | "rule_changed" | "rejected";

export type WorkingLine = {
  id: string; working_id: string; chain_key: string | null; compare: "value" | "rate"; label: string; value: string;
  scale: string; unit: string; page: number; quote: string; theirs: string | null; ours: string | null;
  ours_unit: string | null; difference: string | null; status: LineStatus; note: string | null;
  kind: "yours" | "regulatory" | "computed" | null; created_by: string; created_at: string;
};

export type Working = {
  id: string; connection_id: string; filename: string; pages: { page: number; name: string }[];
  uploaded_by: string; created_at: string; lines: WorkingLine[];
};

export type Proposal = {
  id: string; connection_id: string; working_line_id: string | null; rule_id: string; family: string;
  jurisdiction_id: string; rule_label: string | null; pointer: string; current: string | null; proposed: string;
  unit: string; reason: string; status: "open" | "accepted" | "rejected"; proposed_by: string; created_at: string;
  decided_by: string | null; decided_at: string | null; decision_note: string | null; draft_version_id: string | null;
};

export type AuditMessage = { id: string; role: "user" | "assistant" | "action"; content: string; data: Record<string, unknown>; actor: string; created_at: string };

export type AuditOut = { workings: Working[]; messages: AuditMessage[]; proposals: Proposal[] };

export type RerunOut = { scenario_id: string; scenario: string; run_id: string; status: string };

export const STATUS_LABEL: Record<LineStatus, string> = {
  open: "open",
  matches: "agrees",
  differs: "differs",
  unmatched: "not in the plan",
  ours_accepted: "plan's figure accepted",
  stated: "your figure used",
  proposed: "with an analyst",
  rule_changed: "rule change drafted",
  rejected: "rule kept",
};

export const STATUS_TONE: Partial<Record<LineStatus, string>> = {
  matches: "eg-chip--solid",
  differs: "eg-chip--warning",
  unmatched: "eg-chip--negative",
  proposed: "eg-chip--accent",
  stated: "eg-chip--accent",
  rule_changed: "eg-chip--accent",
};

export const KIND_WORDS: Record<string, string> = {
  price: "Price",
  charge: "Charge at injection",
  exemption: "Exemption",
  loss: "Loss",
  capacity: "Capacity charge",
  drawal: "Charge at drawal",
  banking: "Banking",
  extra: "Other",
};

// the latest line set against each link, for the chain's "theirs" column
export function linesByKey(workings: Working[]): Record<string, WorkingLine> {
  const out: Record<string, WorkingLine> = {};
  for (const w of workings) for (const l of w.lines) if (l.chain_key) out[l.chain_key] = l;
  return out;
}

export function fmt(v: string | number | null | undefined, unit?: string | null): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  if (n < 0 && (unit === "INR" || unit === "INR/kWh")) return `−${fmt(-n, unit)}`;
  if (unit === "INR") return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  if (unit === "INR/kWh") return `₹${n.toFixed(3)}`;
  if (unit === "percent") return `${n.toLocaleString("en-IN", { maximumFractionDigits: 3 })}%`;
  if (unit === "kWh") return `${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })} kWh`;
  if (unit === "kW") return `${n.toLocaleString("en-IN", { maximumFractionDigits: 1 })} kW`;
  return `${n.toLocaleString("en-IN", { maximumFractionDigits: 4 })}${unit ? ` ${unit}` : ""}`;
}
