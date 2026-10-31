"use client";

import { useState } from "react";
import { analystFetch } from "@/lib/analyst";
import { uniqueRefs } from "@/lib/cost";
import type { SourcedValue } from "@/lib/intake";
import { RefChips } from "./RefChips";

type MonthOut = { month: string; consumption: string; setoff: Record<string, string>; banked: string; charge: string; withdrawn: string; lapsed: string; grid: string; unbanked: string; balances: Record<string, string> };
type SettleOut = { rule: string | null; granularity: string; profile_version: number; sources: Record<string, string | null>[]; statement: SourcedValue[]; months: MonthOut[]; notes: string[] };

const KINDS = ["oa_solar_intra", "oa_wind_intra", "oa_hybrid_intra", "oa_solar_ists", "oa_wind_ists", "oa_hybrid_ists"];

const mwh = (v: string | number) => (Number(v) / 1000).toLocaleString("en-IN", { maximumFractionDigits: 1 });

// Analyst: settle a set of open-access sources against the site's load under the approved settlement rule
// and watch each month's bank buckets fill and drain.
export function SettlementExplorer({ connectionId }: { connectionId: string }) {
  const [rows, setRows] = useState([{ id: "solar", kind: "oa_solar_intra", capacity_mw: "2", ownership: "captive" }]);
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState<SettleOut | null>(null);
  const [error, setError] = useState("");

  async function run() {
    setBusy(true);
    setError("");
    try {
      setOut(await analystFetch<SettleOut>(`/connections/${connectionId}/settle`, { method: "POST", body: JSON.stringify({ sources: rows }) }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const peak = out ? Math.max(...out.months.map((m) => Number(m.consumption)), 1) : 1;
  return (
    <>
      <section className="eg-card ep-panel">
        <div className="eg-overline" style={{ marginBottom: 12 }}>Sources to settle</div>
        {rows.map((r, i) => (
          <div key={i} className="ep-form" style={{ marginBottom: 8 }}>
            <label className="eg-field"><span className="eg-field__label">Name</span>
              <span className="eg-input"><input value={r.id} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, id: e.target.value } : x)))} /></span></label>
            <label className="eg-field"><span className="eg-field__label">Source</span>
              <span className="eg-input"><select value={r.kind} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, kind: e.target.value } : x)))}>
                {KINDS.map((k) => <option key={k}>{k}</option>)}</select></span></label>
            <label className="eg-field"><span className="eg-field__label">Capacity (MW)</span>
              <span className="eg-input"><input inputMode="decimal" value={r.capacity_mw} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, capacity_mw: e.target.value } : x)))} /></span></label>
            <label className="eg-field"><span className="eg-field__label">Ownership</span>
              <span className="eg-input"><select value={r.ownership} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, ownership: e.target.value } : x)))}>
                <option>captive</option><option>group_captive</option><option>third_party</option></select></span></label>
          </div>
        ))}
        <div className="ep-row">
          <button className="eg-btn eg-btn--ghost eg-btn--sm" onClick={() => setRows([...rows, { id: `src${rows.length + 1}`, kind: "oa_wind_intra", capacity_mw: "1", ownership: "captive" }])}>Add a source</button>
          <button className="eg-btn eg-btn--primary" disabled={busy} onClick={run}>{busy ? "Settling…" : "Settle the year"}</button>
        </div>
        {error && <p className="ep-error">{error}</p>}
      </section>
      {out && (
        <>
          <section className="eg-glass ep-panel">
            <div className="eg-card__head"><div>
              <h2 className="eg-card__title">The year, settled</h2>
              <p className="eg-card__sub">{out.rule ?? "No settlement rule applies"} · netting: {out.granularity.replaceAll("_", " ")} · load profile v{out.profile_version}</p>
            </div></div>
            <table className="ep-table">
              <tbody>
                {out.statement.map((l) => (
                  <tr key={l.label}><td>{l.label}</td><td className="num">{mwh(l.value)} MWh</td><td><RefChips refs={uniqueRefs([l])} max={3} /></td></tr>
                ))}
              </tbody>
            </table>
            {out.notes.map((n) => <p key={n} className="eg-muted ep-small">{n}</p>)}
          </section>
          <section className="eg-card ep-panel">
            <div className="eg-overline" style={{ marginBottom: 12 }}>Month by month (MWh)</div>
            <table className="ep-table">
              <thead><tr><th>Month</th><th>Where consumption came from</th><th className="num">Banked</th><th className="num">Charge</th><th className="num">Withdrawn</th><th className="num">Lapsed</th><th>Bank at month end</th></tr></thead>
              <tbody>
                {out.months.map((m) => {
                  const set = Object.values(m.setoff).reduce((s, v) => s + Number(v), 0);
                  const w = (v: number) => `${(v / peak) * 100}%`;
                  return (
                    <tr key={m.month}>
                      <td>{m.month.slice(0, 7)}</td>
                      <td>
                        <span className="ep-stack" title={`set off ${mwh(set)} · bank ${mwh(m.withdrawn)} · grid ${mwh(m.grid)}`}>
                          <span className="ep-stack__a" style={{ width: w(set) }} />
                          <span className="ep-stack__b" style={{ width: w(Number(m.withdrawn)) }} />
                          <span className="ep-stack__c" style={{ width: w(Number(m.grid)) }} />
                        </span>
                      </td>
                      <td className="num">{mwh(m.banked)}</td><td className="num">{mwh(m.charge)}</td><td className="num">{mwh(m.withdrawn)}</td>
                      <td className="num">{mwh(m.lapsed)}</td>
                      <td className="ep-small">{Object.entries(m.balances).map(([k, v]) => `${k} ${mwh(v)}`).join(" · ") || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="eg-muted ep-small"><span className="ep-key ep-stack__a" /> set off directly <span className="ep-key ep-stack__b" /> from the bank <span className="ep-key ep-stack__c" /> from the DISCOM</p>
          </section>
        </>
      )}
    </>
  );
}
