"use client";

import { useState } from "react";
import type { WhatIfOut } from "@/lib/plan";
import type { SourcedValue } from "@/lib/intake";

type Editable = { tool: string; source: string | null; label: string; value: SourcedValue };

// Editable assumption chips: change a price or the contract demand and the plan is dispatched and
// settled again (hourly check); the answer is the engine's sentence and numbers.
export function WhatIf({ token, editable }: { token: string; editable: Editable[] }) {
  const [vals, setVals] = useState<Record<string, string>>(() => Object.fromEntries(editable.map((e) => [e.label, String(Number(e.value.value))])));
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState<WhatIfOut | null>(null);
  const [error, setError] = useState("");

  async function run() {
    setBusy(true);
    setError("");
    const body: Record<string, unknown> = { prices: {} };
    for (const e of editable) {
      const v = vals[e.label];
      if (v === undefined || v === "" || Number(v) === Number(e.value.value)) continue;
      if (e.tool === "set_price" && e.source) (body.prices as Record<string, string>)[e.source] = v;
      if (e.tool === "set_contract_demand") body.contract_demand_kva = v;
    }
    try {
      const r = await fetch(`/api/p/${token}/whatif`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const d = await r.json();
      if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : `${r.status}`);
      setOut(d as WhatIfOut);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="ep-form">
        {editable.map((e) => {
          const assumed = e.value.source_refs.some((r) => r.kind === "assumption");
          return (
            <label key={e.label} className="eg-field">
              <span className="eg-field__label">{e.label} <span className={`eg-chip ${assumed ? "eg-chip--warning" : ""}`}>{assumed ? "assumed" : "you said"}</span></span>
              <span className="eg-input"><input inputMode="decimal" value={vals[e.label] ?? ""} onChange={(ev) => setVals({ ...vals, [e.label]: ev.target.value })} /></span>
            </label>
          );
        })}
      </div>
      <div className="ep-row">
        <button className="eg-btn eg-btn--primary" disabled={busy} onClick={run}>{busy ? "Settling the change…" : "What if?"}</button>
        <span className="eg-muted ep-small">Sizes held; the year is dispatched and settled again hourly.</span>
      </div>
      {out && <p className="ep-answer">{out.sentence}</p>}
      {error && <p className="ep-error">{error}</p>}
    </div>
  );
}
