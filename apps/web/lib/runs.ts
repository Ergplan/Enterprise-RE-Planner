import type { Ref, SourcedValue } from "./intake";

export type SizeOut = {
  id: string; kind: string; label: string; kw: SourcedValue; kwh: SourcedValue | null; delivered_kwh: SourcedValue | null;
  setoff_kwh: SourcedValue | null; energy_cost: SourcedValue | null; banked_kwh: SourcedValue | null; unbanked_kwh: SourcedValue | null;
  waterfall: Record<string, SourcedValue[]>; gaps: string[];
};
export type SummaryOut = {
  sizes: SizeOut[];
  annual: { before: SourcedValue; after: SourcedValue; saving: SourcedValue; capex: SourcedValue };
  payback_years: SourcedValue | null; irr_pct: SourcedValue | null;
  emissions: { factor: SourcedValue; before_t: SourcedValue; after_t: SourcedValue };
  settlement: { grid_kwh: SourcedValue; lapsed_kwh: SourcedValue; withdrawn_kwh: SourcedValue; rule: string | null };
  contract_demand_kva: SourcedValue;
  binding: { name: string; words: string; refs: SourcedValue[] }[];
  provenance: { load_profile: string; prices: string[]; profile_ref: SourcedValue };
  sensitivities: { label: string; saving: SourcedValue }[];
  notes: string[];
};
export type RunOut = {
  id: string; scenario_id: string; status: "queued" | "running" | "done" | "failed" | "failed_resettle"; resolution_min: number;
  created_at: string; finished_at: string | null; error: string | null; replay_of: string | null;
  pins: Record<string, unknown>; solver: { status?: string; gap?: number | null; seconds?: number; blocks?: number; objective_inr?: string };
  summary: SummaryOut | null; analyst: { resettle: { agrees: boolean; max_diff_kwh: string; tolerance_kwh: string; solver_objective_inr: string; resettled_cost_inr: string } } | null;
  identical_to_original: boolean | null;
};
export type CandidateSpec = { kind: string; ownership?: string; price_inr_per_kwh?: string; max_mw?: string; min_mw?: string };
export type ScenarioSpec = { candidates: CandidateSpec[]; as_of?: string | null; resolution_min: 15 | 60; sensitivities?: { kind: string; candidate?: string; pct: string[] }[] };
export type ScenarioOut = { id: string; site_id: string; connection_id: string; name: string; spec: ScenarioSpec; created_at: string; latest_run: RunOut | null };
export type DispatchOut = { run_id: string; start: string; minutes: number; times: string[]; slots: string[]; series: Record<string, SourcedValue[]> };

export const refsOf = (...v: (SourcedValue | null | undefined)[]): Ref[] => v.flatMap((x) => x?.source_refs ?? []);

export function mw(kw: SourcedValue | null | undefined): string {
  if (!kw) return "—";
  return (Number(kw.value) / 1000).toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

export function crore(v: SourcedValue | null | undefined): string {
  if (!v) return "—";
  return `₹${(Number(v.value) / 1e7).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} cr`;
}

// Three starting scenarios for a site: captive solar; third-party hybrid with a battery; rooftop, solar and a battery.
export function presets(asOf: string, minutes: 15 | 60): { name: string; spec: ScenarioSpec }[] {
  const base = { as_of: asOf, resolution_min: minutes };
  return [
    { name: "Captive solar", spec: { ...base, candidates: [{ kind: "oa_solar_intra", ownership: "captive" }], sensitivities: [{ kind: "price", candidate: "oa_solar_intra", pct: ["-10", "10"] }] } },
    { name: "Hybrid + battery", spec: { ...base, candidates: [{ kind: "oa_hybrid_intra", ownership: "third_party" }, { kind: "btm_bess" }], sensitivities: [{ kind: "price", candidate: "oa_hybrid_intra", pct: ["-10", "10"] }] } },
    { name: "Rooftop + solar + battery", spec: { ...base, candidates: [{ kind: "rooftop_pv" }, { kind: "oa_solar_intra", ownership: "captive" }, { kind: "btm_bess" }], sensitivities: [{ kind: "grid_rate", pct: ["-5", "5"] }] } },
  ];
}
