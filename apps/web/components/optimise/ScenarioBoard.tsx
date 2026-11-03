"use client";

import { useCallback, useEffect, useState } from "react";
import { analystFetch, getAnalyst } from "@/lib/analyst";
import { uniqueRefs } from "@/lib/cost";
import type { DispatchOut, RunOut, ScenarioOut } from "@/lib/runs";
import { crore, mw, mwh, presets, refsOf } from "@/lib/runs";
import type { MonthMix, SizeOut } from "@/lib/runs";
import { RefChips } from "../cost/RefChips";
import { DispatchWeek } from "./DispatchWeek";
import { MixBuilder } from "./MixBuilder";

const STATUS: Record<string, string> = {
  queued: "Queued",
  running: "Solving…",
  done: "Settled",
  failed: "Failed",
  failed_resettle: "Re-settlement disagreed",
};

async function get<T>(path: string): Promise<T> {
  const actor = getAnalyst();
  const r = await fetch(`/api${path}`, { headers: actor ? { "X-Ergplan-Actor": actor, "X-Ergplan-Role": "analyst" } : {} });
  if (!r.ok) throw new Error(`${r.status}`);
  return (await r.json()) as T;
}

// Journey step 5: scenarios side by side (sizes, saving, payback), the settled dispatch for a week, and what
// held each answer where it is. Analysts create and run scenarios; clients read settled runs.
export function ScenarioBoard({ siteId, connectionId, initial, asOf }: { siteId: string; connectionId: string; initial: ScenarioOut[]; asOf: string }) {
  const [scenarios, setScenarios] = useState(initial);
  const [minutes, setMinutes] = useState<15 | 60>(15);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string | null>(initial.find((s) => s.latest_run?.status === "done")?.latest_run?.id ?? null);
  const [week, setWeek] = useState<string>("");
  const [dispatch, setDispatch] = useState<DispatchOut | null>(null);

  const refresh = useCallback(async () => {
    setScenarios(await get<ScenarioOut[]>(`/sites/${siteId}/scenarios`));
  }, [siteId]);

  const pending = scenarios.some((s) => s.latest_run && ["queued", "running"].includes(s.latest_run.status));
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(() => void refresh().catch(() => undefined), 3000);
    return () => clearInterval(t);
  }, [pending, refresh]);

  useEffect(() => {
    if (!selected) return;
    const q = week ? `?start=${week}` : "";
    get<DispatchOut>(`/runs/${selected}/dispatch${q}`).then(setDispatch).catch(() => setDispatch(null));
  }, [selected, week]);

  async function createPresets() {
    setBusy("create");
    setError("");
    try {
      for (const p of presets(asOf, minutes)) {
        const sc = await analystFetch<ScenarioOut>(`/sites/${siteId}/scenarios`, { method: "POST", body: JSON.stringify({ connection_id: connectionId, name: p.name, spec: p.spec }) });
        await analystFetch<RunOut>(`/scenarios/${sc.id}/run`, { method: "POST" });
      }
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function rerun(id: string) {
    setBusy(id);
    setError("");
    try {
      await analystFetch<RunOut>(`/scenarios/${id}/run`, { method: "POST" });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  const run = scenarios.map((s) => s.latest_run).find((r) => r?.id === selected) ?? null;
  const [analyst, setAnalyst] = useState(false);
  useEffect(() => setAnalyst(Boolean(getAnalystSafe())), []); // after hydration: storage is browser-only
  return (
    <>
      <MixBuilder connectionId={connectionId} asOf={asOf} defaultOwnership={null} onQueued={() => void refresh()} />
      {analyst && (
        <section className="eg-card ep-panel">
          <div className="ep-row">
            <div className="eg-seg eg-seg--sm" role="group" aria-label="Resolution">
              {([15, 60] as const).map((m) => (
                <button key={m} className="ep-seglink" aria-current={minutes === m ? "true" : undefined} onClick={() => setMinutes(m)}>{m === 15 ? "15 minutes" : "Hourly preview"}</button>
              ))}
            </div>
            <button className="eg-btn eg-btn--primary" disabled={busy !== ""} onClick={createPresets}>{busy === "create" ? "Queuing…" : "Size three standard scenarios"}</button>
            <span className="eg-muted ep-small">Captive solar · hybrid + battery · rooftop + solar + battery, at the rules in force on {asOf}. A 15-minute year takes about a minute each on the worker.</span>
          </div>
          {error && <p className="ep-error">{error}</p>}
        </section>
      )}
      {scenarios.length === 0 && <p className="ep-empty">No scenarios yet. Build your mix above.</p>}
      <div className="ep-scenarios">
        {scenarios.map((sc) => {
          const r = sc.latest_run;
          const s = r?.summary;
          return (
            <article key={sc.id} className={`eg-card ep-panel ep-scenario${r?.id === selected ? " ep-scenario--on" : ""}`}>
              <div className="eg-card__head">
                <div>
                  <h2 className="eg-card__title">{sc.name}</h2>
                  <p className="eg-card__sub">{r ? `${STATUS[r.status] ?? r.status}${r.solver.seconds ? ` · ${r.solver.seconds}s` : ""} · ${r.resolution_min === 15 ? "15-minute" : "hourly"}` : "Not run"}</p>
                </div>
                {analyst && <button className="eg-btn eg-btn--ghost eg-btn--sm" disabled={busy !== ""} onClick={() => rerun(sc.id)}>Run</button>}
              </div>
              {s ? (
                <>
                  <div className="ep-stat-big">
                    <div className="eg-overline">Saving a year</div>
                    <div className="ep-big num">{crore(s.annual.saving)}</div>
                    <RefChips refs={uniqueRefs([s.annual.saving])} max={2} />
                  </div>
                  <table className="ep-table ep-small">
                    <tbody>
                      {s.sizes.map((z) => <SizeRow key={z.id} z={z} />)}
                      <tr><td>Cost today → with plan</td><td className="num">{crore(s.annual.before)} → {crore(s.annual.after)}</td></tr>
                      <tr><td>Payback</td><td className="num">{s.payback_years ? `${Number(s.payback_years.value).toFixed(1)} years` : "—"}</td></tr>
                      <tr><td>IRR</td><td className="num">{s.irr_pct ? `${Number(s.irr_pct.value).toFixed(1)}%` : "—"}</td></tr>
                      <tr><td>Grid CO₂</td><td className="num">{Math.round(Number(s.emissions.before_t.value)).toLocaleString("en-IN")} → {Math.round(Number(s.emissions.after_t.value)).toLocaleString("en-IN")} t</td></tr>
                    </tbody>
                  </table>
                  {s.sizes.some((z) => z.gaps.length) && (
                    <p className="ep-small eg-muted">Not yet sourced: {[...new Set(s.sizes.flatMap((z) => z.gaps))].join(", ").replaceAll("_", " ")}</p>
                  )}
                  {r && <button className="eg-btn eg-btn--ghost eg-btn--sm" onClick={() => { setSelected(r.id); setWeek(""); }}>{r.id === selected ? "Shown below" : "See the dispatch"}</button>}
                </>
              ) : r?.status === "failed" || r?.status === "failed_resettle" ? (
                <p className="ep-error ep-small">{r.error ?? "This run did not finish."}</p>
              ) : (
                <p className="eg-muted ep-small">{r ? "Working…" : ""}</p>
              )}
            </article>
          );
        })}
      </div>
      {run?.summary && (
        <>
          <section className="eg-glass ep-panel">
            <div className="eg-card__head">
              <div>
                <h2 className="eg-card__title">A week of the settled dispatch</h2>
                <p className="eg-card__sub">{dispatch ? `${dispatch.times[0]?.slice(0, 10)} onwards, ${dispatch.minutes}-minute blocks. ` : ""}Shown after re-settlement under {run.summary.settlement.rule ?? "block-by-block netting"}; the peak-load week unless you pick one.</p>
              </div>
              <label className="eg-field"><span className="eg-field__label">Week from</span>
                <span className="eg-input"><input type="date" value={week} onChange={(e) => setWeek(e.target.value)} /></span></label>
            </div>
            {dispatch ? <DispatchWeek d={dispatch} /> : <p className="eg-muted">Loading…</p>}
          </section>
          {run.summary.monthly && run.summary.monthly.length > 0 && <YearMix months={run.summary.monthly} sizes={run.summary.sizes} />}
          <section className="eg-card ep-panel">
            <div className="eg-overline" style={{ marginBottom: 12 }}>What holds this answer where it is</div>
            {run.summary.binding.length === 0 && <p className="eg-muted ep-small">Nothing binds: the sizes are where the money says.</p>}
            <ul className="ep-list">
              {run.summary.binding.map((b) => (
                <li key={b.name}>{b.words} <RefChips refs={uniqueRefs(b.refs)} max={3} /></li>
              ))}
            </ul>
            {run.summary.sensitivities.length > 0 && (
              <>
                <div className="eg-overline" style={{ margin: "16px 0 8px" }}>If prices move</div>
                <table className="ep-table ep-small"><tbody>
                  {run.summary.sensitivities.map((x) => <tr key={x.label}><td>{x.label}</td><td className="num">{crore(x.saving)} a year</td></tr>)}
                </tbody></table>
              </>
            )}
            <p className="eg-muted ep-small" style={{ marginTop: 12 }}>
              Load profile {run.summary.provenance.load_profile}{run.summary.provenance.prices.length ? ` · IEX vintages ${run.summary.provenance.prices.join(", ")}` : ""} · contract demand {Number(run.summary.contract_demand_kva.value).toLocaleString("en-IN")} kVA.
              <RefChips refs={refsOf(run.summary.emissions.factor)} max={1} />
            </p>
            {run.summary.notes.map((n) => <p key={n} className="eg-muted ep-small">{n}</p>)}
            {run.analyst && (
              <p className="ep-small">
                <span className={`eg-chip ${run.analyst.resettle.agrees ? "eg-chip--success" : "eg-chip--danger"}`}>Judge {run.analyst.resettle.agrees ? "agrees" : "disagrees"} · {run.analyst.resettle.max_diff_kwh} kWh</span>{" "}
                <span className="eg-muted">solver ₹{Number(run.analyst.resettle.solver_objective_inr).toLocaleString("en-IN")} · re-settled ₹{Number(run.analyst.resettle.resettled_cost_inr).toLocaleString("en-IN")} · gap {run.solver.gap ?? 0}</span>
              </p>
            )}
          </section>
        </>
      )}
    </>
  );
}

// One source's size: a plant's capacity; a battery's power and energy; an exchange purchase's peak, energy and price.
function SizeRow({ z }: { z: SizeOut }) {
  if (z.kind === "btm_bess") return <tr><td>{z.label}</td><td className="num">{mw(z.kw)} MW / {mw(z.kwh)} MWh</td></tr>;
  if (z.exchange) {
    return (
      <tr>
        <td>{z.label}<div className="ep-small eg-muted">bought in {Number(z.exchange.hours_bought).toLocaleString("en-IN")} hours at ₹{Number(z.exchange.avg_landed.value).toFixed(2)}/kWh landed · {Number(z.exchange.share_of_load.value).toFixed(1)}% of your use</div></td>
        <td className="num">{mwh(z.delivered_kwh)} MWh<div className="ep-small eg-muted">up to {mw(z.kw)} MW</div></td>
      </tr>
    );
  }
  return (
    <tr>
      <td>{z.label}{z.delivered_kwh && <div className="ep-small eg-muted">{mwh(z.delivered_kwh)} MWh a year at your meter</div>}</td>
      <td className="num">{mw(z.kw)} MW</td>
    </tr>
  );
}

const MIX_COLORS = ["#f5b544", "#4fb3d9", "#7fc97f", "#c084fc", "#f472b6", "#94a3b8", "#fb923c"];

// Where each month's consumption came from, as the judge settled it.
function YearMix({ months, sizes }: { months: MonthMix[]; sizes: SizeOut[] }) {
  const label = Object.fromEntries(sizes.map((z) => [z.id, z.label]));
  const ids = [...new Set(months.flatMap((m) => Object.keys(m.sources)))].filter((id) => months.some((m) => Number(m.sources[id]?.value ?? 0) > 0));
  const layers = [
    ...ids.map((id, i) => ({ key: id, label: label[id] ?? id, color: MIX_COLORS[i % MIX_COLORS.length], v: (m: MonthMix) => Number(m.sources[id]?.value ?? 0) })),
    { key: "bank", label: "From the bank", color: "#a3e635", v: (m: MonthMix) => Number(m.withdrawn_kwh.value) },
    { key: "grid", label: "From the DISCOM", color: "#64748b", v: (m: MonthMix) => Number(m.grid_kwh.value) },
  ];
  const max = Math.max(...months.map((m) => Number(m.load_kwh.value)), 1);
  const total = (f: (m: MonthMix) => number) => months.reduce((a, m) => a + f(m), 0);
  const load = total((m) => Number(m.load_kwh.value));
  return (
    <section className="eg-card ep-panel">
      <div className="eg-card__head">
        <div>
          <h2 className="eg-card__title">Your year, month by month</h2>
          <p className="eg-card__sub">Where each month&apos;s consumption comes from once the year is settled under the state&apos;s rules (MWh).</p>
        </div>
      </div>
      <div className="ep-yearmix" role="img" aria-label="Monthly energy mix">
        {months.map((m) => (
          <div key={m.month} className="ep-yearmix__col">
            <div className="ep-yearmix__bar" style={{ height: `${(Number(m.load_kwh.value) / max) * 100}%` }}>
              {layers.map((l) => {
                const v = l.v(m);
                return v > 0 ? <span key={l.key} title={`${l.label}: ${(v / 1000).toFixed(0)} MWh`} style={{ flexGrow: v, background: l.color }} /> : null;
              })}
            </div>
            <span className="ep-small eg-muted">{new Date(m.month).toLocaleString("en-IN", { month: "short" })}</span>
          </div>
        ))}
      </div>
      <div className="ep-legend ep-small">
        {layers.map((l) => (
          <span key={l.key}><span style={{ display: "inline-block", width: 10, height: 10, background: l.color, borderRadius: 2, marginRight: 4 }} />{l.label} · {(total(l.v) / 1000).toLocaleString("en-IN", { maximumFractionDigits: 0 })} MWh ({load > 0 ? ((total(l.v) / load) * 100).toFixed(1) : "0"}%)</span>
        ))}
      </div>
    </section>
  );
}

function getAnalystSafe(): string {
  try {
    return getAnalyst();
  } catch {
    return "";
  }
}
