"use client";

import { useState } from "react";
import { CATEGORIES, DISCOMS, stated, type MonthFacts, type SiteIntake } from "@/lib/intake";

type Row = { month: string; kwh: string; kva: string; pf: string };

function lastMonths(n: number): string[] {
  const out: string[] = [];
  const d = new Date();
  for (let i = n; i >= 1; i--) {
    const x = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() - i, 1));
    out.push(x.toISOString().slice(0, 7));
  }
  return out;
}

// The third door: type the facts. Everything typed is "you said"; what is left out is assumed later.
export function TypeFacts({ onReady }: { onReady: (si: SiteIntake) => void }) {
  const [company, setCompany] = useState("");
  const [discom, setDiscom] = useState("npcl");
  const state = DISCOMS.find((d) => d.id === discom)?.state ?? "UP";
  const [category, setCategory] = useState("HV-2");
  const [voltage, setVoltage] = useState("11");
  const [cd, setCd] = useState("");
  const [rows, setRows] = useState<Row[]>(lastMonths(3).map((m) => ({ month: m, kwh: "", kva: "", pf: "" })));
  const [error, setError] = useState("");

  function next() {
    const months: MonthFacts[] = rows
      .filter((r) => r.kwh.trim())
      .map((r) => ({
        month: `${r.month}-01`,
        energy: stated(r.kwh.replaceAll(",", "").trim()),
        energy_unit: "kWh",
        tod: [],
        max_kva: r.kva.trim() ? stated(r.kva.replaceAll(",", "").trim()) : null,
        power_factor: r.pf.trim() ? stated(r.pf.trim()) : null,
        shutdown_days: [],
        unmapped_tod_slots: [],
      }));
    if (!company.trim() || !cd.trim() || months.length === 0) {
      setError("Give the company name, the contract demand and at least one month's energy.");
      return;
    }
    setError("");
    onReady({
      client_name: stated(company.trim()),
      site_name: stated(`${company.trim()} · ${discom.toUpperCase()}`),
      state: stated(state),
      discom: stated(discom),
      category: stated(category),
      voltage_kv: stated(voltage),
      contract_demand_kva: stated(cd.replaceAll(",", "").trim()),
      industry_shape: { value: "two_shift", provenance: "assumption", ref: { kind: "assumption", note: "operating pattern not stated; two shifts, six days a week assumed" } },
      weekly_off: { value: [6], provenance: "assumption", ref: { kind: "assumption", note: "weekly off not stated; Sunday assumed" } },
      months,
      assets: [],
    });
  }

  const setRow = (i: number, k: keyof Row, v: string) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <section className="eg-card ep-panel">
      <div className="ep-form">
        <label className="eg-field"><span className="eg-field__label">Company</span>
          <span className="eg-input"><input value={company} onChange={(e) => setCompany(e.target.value)} /></span></label>
        <label className="eg-field"><span className="eg-field__label">DISCOM</span>
          <span className="eg-input"><select value={discom} onChange={(e) => {
            setDiscom(e.target.value);
            const st = DISCOMS.find((d) => d.id === e.target.value)?.state ?? "UP";
            setCategory(CATEGORIES[st][0]);
          }}>{DISCOMS.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></span></label>
        <label className="eg-field"><span className="eg-field__label">Tariff category</span>
          <span className="eg-input"><select value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES[state].map((c) => <option key={c}>{c}</option>)}</select></span></label>
        <label className="eg-field"><span className="eg-field__label">Supply voltage (kV)</span>
          <span className="eg-input"><input inputMode="decimal" value={voltage} onChange={(e) => setVoltage(e.target.value)} /></span></label>
        <label className="eg-field"><span className="eg-field__label">Contract demand (kVA)</span>
          <span className="eg-input"><input inputMode="decimal" value={cd} onChange={(e) => setCd(e.target.value)} /></span></label>
      </div>
      <table className="ep-table" style={{ marginTop: "var(--space-6)" }}>
        <thead><tr><th>Month</th><th>Energy (kWh)</th><th>Max demand (kVA)</th><th>Power factor</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td><span className="eg-input"><input type="month" aria-label="Month" value={r.month} onChange={(e) => setRow(i, "month", e.target.value)} /></span></td>
              <td><span className="eg-input"><input inputMode="decimal" aria-label="Energy" value={r.kwh} onChange={(e) => setRow(i, "kwh", e.target.value)} /></span></td>
              <td><span className="eg-input"><input inputMode="decimal" aria-label="Max demand" value={r.kva} onChange={(e) => setRow(i, "kva", e.target.value)} /></span></td>
              <td><span className="eg-input"><input inputMode="decimal" aria-label="Power factor" value={r.pf} onChange={(e) => setRow(i, "pf", e.target.value)} /></span></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="ep-row" style={{ marginTop: "var(--space-4)" }}>
        {rows.length < 12 && (
          <button className="eg-btn eg-btn--ghost eg-btn--sm" onClick={() => {
            const last = rows[rows.length - 1]?.month ?? lastMonths(1)[0];
            const [y, m] = last.split("-").map(Number);
            const nx = new Date(Date.UTC(y, m, 1)).toISOString().slice(0, 7);
            setRows([...rows, { month: nx, kwh: "", kva: "", pf: "" }]);
          }}>Add a month</button>
        )}
        <button className="eg-btn eg-btn--primary" onClick={next}>Continue</button>
      </div>
      {error && <p className="ep-error">{error}</p>}
    </section>
  );
}
