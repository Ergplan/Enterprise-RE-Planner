import type { Ref, SourcedValue } from "./intake";
import type { SummaryOut } from "./runs";

export type ScenarioPlan = { scenario_id: string; name: string; run_id: string; resolution_min: number; finished_at: string | null; summary: SummaryOut; analyst?: Record<string, unknown> | null };
export type PlanOut = {
  token: string | null; connection_id: string; client: string; site: string; state: string; discom: string; category: string | null; voltage_kv: string | null;
  profile: string | null; scenarios: ScenarioPlan[]; recommended: string | null; pending_runs: number;
  documents: { id: string; title: string; regulator: string | null; url_public: string | null; url: string; pages: number[] }[];
  assumptions: { note: string; ref: Ref; label?: string; value?: string; unit?: string }[];
  editable: { tool: string; source: string | null; label: string; value: SourcedValue }[];
  analyst_view: boolean;
};
export type WhatIfOut = { described: string; sentence: string; resolution_min: number; annual: Record<string, SourcedValue>; base_saving: SourcedValue };

// Numbered citations for the printed plan: each distinct document page once, in order of first use.
export class Citations {
  private keys: string[] = [];
  readonly notes: Ref[] = [];
  cite(refs: Ref[]): number[] {
    const out: number[] = [];
    for (const r of refs) {
      if (!(r.kind === "order" || r.kind === "regulation") || !r.document_id) continue;
      const k = `${r.document_id}#${r.page ?? ""}`;
      let i = this.keys.indexOf(k);
      if (i < 0) {
        this.keys.push(k);
        this.notes.push(r);
        i = this.keys.length - 1;
      }
      if (!out.includes(i + 1)) out.push(i + 1);
    }
    return out;
  }
}
