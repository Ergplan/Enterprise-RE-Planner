"use client";

import { useState } from "react";
import type { AssetIn } from "@/lib/intake";

// Existing assets on site (step 4). Fields per kind mirror the API's validated params.
export const ASSET_FIELDS: Record<string, { label: string; fields: { key: string; label: string; required?: boolean; kind?: "bool" | "text" }[] }> = {
  rooftop_pv: { label: "Rooftop solar", fields: [{ key: "capacity_kwp", label: "Capacity (kWp)", required: true }] },
  captive_thermal: {
    label: "Captive thermal plant",
    fields: [
      { key: "fuel", label: "Fuel", required: true, kind: "text" },
      { key: "capacity_mw", label: "Capacity (MW)", required: true },
      { key: "technical_minimum_pct", label: "Technical minimum (%)", required: true },
      { key: "variable_cost_inr_per_kwh", label: "Variable cost (₹/kWh)", required: true },
      { key: "heat_rate_kcal_per_kwh", label: "Heat rate (kcal/kWh)" },
      { key: "ramp_up_mw_per_block", label: "Ramp up (MW per 15 min)" },
      { key: "ramp_down_mw_per_block", label: "Ramp down (MW per 15 min)" },
      { key: "min_up_blocks", label: "Minimum up time (blocks)" },
      { key: "min_down_blocks", label: "Minimum down time (blocks)" },
      { key: "aux_consumption_pct", label: "Auxiliary consumption (%)" },
      { key: "must_run", label: "Must run", kind: "bool" },
    ],
  },
  waste_heat: { label: "Waste-heat recovery", fields: [{ key: "capacity_mw", label: "Capacity (MW)", required: true }, { key: "availability_pct", label: "Availability (%)" }] },
  bess: {
    label: "Battery storage",
    fields: [
      { key: "power_mw", label: "Power (MW)", required: true },
      { key: "energy_mwh", label: "Energy (MWh)", required: true },
      { key: "round_trip_efficiency_pct", label: "Round-trip efficiency (%)" },
    ],
  },
  dg: { label: "Diesel generator", fields: [{ key: "capacity_kva", label: "Capacity (kVA)", required: true }, { key: "cost_inr_per_kwh", label: "Running cost (₹/kWh)" }] },
};

export function AssetsEditor({ assets, onChange }: { assets: AssetIn[]; onChange: (a: AssetIn[]) => void }) {
  const [kind, setKind] = useState("rooftop_pv");
  const [vals, setVals] = useState<Record<string, string>>({});
  const spec = ASSET_FIELDS[kind];
  const missing = spec.fields.filter((f) => f.required && !vals[f.key]?.trim());

  function add() {
    const params: Record<string, unknown> = {};
    for (const f of spec.fields) {
      const v = vals[f.key]?.trim();
      if (!v) continue;
      params[f.key] = f.kind === "bool" ? v === "yes" : v;
    }
    onChange([...assets, { kind, params, provenance: "client_stated" }]);
    setVals({});
  }

  return (
    <div className="ep-assets">
      {assets.length === 0 ? (
        <p className="eg-muted">No existing generation or storage recorded.</p>
      ) : (
        <table className="ep-table">
          <tbody>
            {assets.map((a, i) => (
              <tr key={i}>
                <td>{ASSET_FIELDS[a.kind]?.label ?? a.kind}</td>
                <td className="eg-muted">{Object.entries(a.params).map(([k, v]) => `${k.replaceAll("_", " ")} ${String(v)}`).join(" · ")}</td>
                <td className="num"><button className="eg-btn eg-btn--ghost eg-btn--sm" onClick={() => onChange(assets.filter((_, j) => j !== i))}>Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="ep-form" style={{ marginTop: "var(--space-4)" }}>
        <label className="eg-field"><span className="eg-field__label">Add</span>
          <span className="eg-input"><select value={kind} onChange={(e) => { setKind(e.target.value); setVals({}); }}>
            {Object.entries(ASSET_FIELDS).map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
          </select></span></label>
        {spec.fields.map((f) => (
          <label key={f.key} className="eg-field"><span className="eg-field__label">{f.label}{f.required ? "" : " (optional)"}</span>
            <span className="eg-input">
              {f.kind === "bool" ? (
                <select value={vals[f.key] ?? "no"} onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })}>
                  <option value="no">No</option><option value="yes">Yes</option>
                </select>
              ) : (
                <input inputMode={f.kind === "text" ? "text" : "decimal"} value={vals[f.key] ?? ""} onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })} />
              )}
            </span></label>
        ))}
      </div>
      <div className="ep-row" style={{ marginTop: "var(--space-3)" }}>
        <button className="eg-btn eg-btn--ghost eg-btn--sm" disabled={missing.length > 0} onClick={add}>Add {spec.label.toLowerCase()}</button>
      </div>
    </div>
  );
}
