"use client";

import { useMemo, useState } from "react";
import { RefChips } from "@/components/cost/RefChips";
import { inr, num } from "@/lib/evaluate";
import type { Ref, SourcedValue } from "@/lib/intake";
import type { Chain } from "@/lib/audit";
import type { DispatchOut, LifecycleOut, MonthMix, RunOut, SizeOut, SummaryOut } from "@/lib/runs";

export const MIX_COLORS = ["#f5b544", "#4fb3d9", "#7fc97f", "#c084fc", "#f472b6", "#94a3b8", "#fb923c"];
const V = (x: SourcedValue | null | undefined) => (x ? Number(x.value) : 0);
const uniq = (refs: Ref[]): Ref[] => {
  const seen = new Set<string>();
  return refs.filter((r) => { const k = `${r.kind}|${r.document_id ?? ""}|${r.page ?? ""}|${r.note ?? ""}`; if (seen.has(k)) return false; seen.add(k); return true; });
};

// 1. The headline: saving, costs, NPV, payback, green share, emissions.
export function Summary({ s, years }: { s: SummaryOut; years: number }) {
  const before = V(s.annual.before), after = V(s.annual.after), saving = V(s.annual.saving);
  const pct = before > 0 ? (saving / before) * 100 : 0;
  const lc = s.lifecycle;
  const load = s.monthly?.reduce((a, m) => a + V(m.load_kwh), 0) ?? 0;
  const grid = V(s.settlement.grid_kwh);
  const green = load > 0 ? ((load - grid) / load) * 100 : 0;
  const co2 = V(s.emissions.before_t) - V(s.emissions.after_t);
  return (
    <div className="ep-kpis">
      <div className="eg-stat eg-stat--hero">
        <span className="eg-stat__label">Saving in year one</span>
        <span className="eg-stat__value">{inr(saving)}</span>
        <span className="eg-stat__foot">{pct.toFixed(1)}% of today&apos;s {inr(before)} <RefChips refs={uniq(s.annual.saving.source_refs)} max={1} /></span>
      </div>
      <div className="eg-stat">
        <span className="eg-stat__label">Cost with the plan, year one</span>
        <span className="eg-stat__value">{inr(after)}</span>
        <span className="eg-stat__foot">against {inr(before)} today</span>
      </div>
      {lc && (
        <div className="eg-stat">
          <span className="eg-stat__label">Net present value, {years} years</span>
          <span className="eg-stat__value">{inr(lc.npv?.value)}</span>
          <span className="eg-stat__foot">{inr(lc.nominal_saving?.value)} undiscounted</span>
        </div>
      )}
      {lc?.capex && Number(lc.capex.value) > 0 && (
        <div className="eg-stat">
          <span className="eg-stat__label">Capital and payback</span>
          <span className="eg-stat__value">{inr(lc.capex.value)}</span>
          <span className="eg-stat__foot">{lc.simple_payback_years ? `pays back in ${Number(lc.simple_payback_years.value).toFixed(1)} years` : "no payback in the period"}{lc.irr_pct ? ` · IRR ${Number(lc.irr_pct.value).toFixed(1)}%` : ""}</span>
        </div>
      )}
      <div className="eg-stat">
        <span className="eg-stat__label">Green share of consumption</span>
        <span className="eg-stat__value">{green.toFixed(0)}%</span>
        <span className="eg-stat__foot">{num((load - grid) / 1000)} of {num(load / 1000)} MWh a year</span>
      </div>
      <div className="eg-stat">
        <span className="eg-stat__label">CO₂ avoided a year</span>
        <span className="eg-stat__value">{num(co2)} t</span>
        <span className="eg-stat__foot">at {Number(s.emissions.factor.value).toFixed(2)} t/MWh <RefChips refs={uniq(s.emissions.factor.source_refs)} max={1} /></span>
      </div>
    </div>
  );
}

// 2. Recommended system: each source's size, energy, landed cost, cost for the year.
export function Sizes({ s, chain }: { s: SummaryOut; chain: Chain | null }) {
  const landed = Object.fromEntries((chain?.sources ?? []).map((x) => [x.id, x.landed_total]));
  const load = s.monthly?.reduce((a, m) => a + V(m.load_kwh), 0) ?? 0;
  return (
    <div className="ep-scroll">
      <table className="ep-table ep-sizes">
        <thead>
          <tr><th>Source</th><th className="num">Recommended size</th><th className="num">Energy a year</th><th className="num">Share of use</th><th className="num">Landed at your meter</th><th className="num">Cost a year</th><th>Source of the figures</th></tr>
        </thead>
        <tbody>
          {s.sizes.map((z) => {
            const energy = z.kind === "btm_bess" ? null : V(z.delivered_kwh);
            const lt = landed[z.id];
            return (
              <tr key={z.id} className={Number(z.kw.value) <= 0 && !(z.kind === "btm_bess" && V(z.kwh) > 0) ? "ep-dim" : undefined}>
                <td>
                  <b>{z.label}</b>
                  {z.ownership && z.kind !== "rooftop_pv" && z.kind !== "btm_bess" && <div className="eg-muted ep-small">{z.ownership.replace("_", " ")}</div>}
                  {z.exchange && <div className="eg-muted ep-small">bought in {num(z.exchange.hours_bought)} hours · never sold</div>}
                  {z.gaps.length > 0 && <div className="eg-muted ep-small">{z.gaps.length} figure{z.gaps.length > 1 ? "s" : ""} not yet sourced</div>}
                </td>
                <td className="num">{sizeText(z)}</td>
                <td className="num">{energy === null ? "—" : `${num(energy / 1000)} MWh`}</td>
                <td className="num">{energy === null || !load ? "—" : `${((energy / load) * 100).toFixed(1)}%`}</td>
                <td className="num">{z.exchange ? `₹${Number(z.exchange.avg_landed.value).toFixed(2)}` : lt ? `₹${Number(lt.value).toFixed(2)}` : z.kind === "rooftop_pv" || z.kind === "btm_bess" ? "—" : "—"}</td>
                <td className="num">{z.energy_cost ? inr(z.energy_cost.value) : lineCost(s, z.id)}</td>
                <td><RefChips refs={uniq([...(z.kw.source_refs ?? []), ...(lt?.source_refs ?? [])])} max={2} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function sizeText(z: SizeOut): string {
  if (z.kind === "btm_bess") return `${(V(z.kw) / 1000).toFixed(2)} MW / ${(V(z.kwh) / 1000).toFixed(2)} MWh`;
  if (z.exchange) return `up to ${(V(z.kw) / 1000).toFixed(2)} MW`;
  return `${(V(z.kw) / 1000).toFixed(2)} MW`;
}

function lineCost(s: SummaryOut, cid: string): string {
  const fixed = s.lines_after?.[`fixed:${cid}`];
  return fixed ? `${inr(fixed)} (annualised)` : "—";
}

const LINE_LABEL: Record<string, string> = { grid_energy: "Grid energy", demand: "Demand charges", excess_demand: "Excess demand penalty" };

// 3. Year-one cost comparison: today against the plan, line by line. The lines come from the chain
// (each carries its source_refs); the summary's analyst-only lines are the fallback.
export function CostTable({ s, chain, print = false }: { s: SummaryOut; chain: Chain | null; print?: boolean }) {
  const names = Object.fromEntries(s.sizes.map((z) => [z.id, z.label]));
  type Row = { key: string; label: string; before: number | null; after: number | null; refs: Ref[] };
  const rows: Row[] = [];
  const put = (key: string, label: string, side: "before" | "after", v: number, refs: Ref[]) => {
    let r = rows.find((x) => x.key === key);
    if (!r) { r = { key, label, before: null, after: null, refs: [] }; rows.push(r); }
    r[side] = v;
    r.refs = uniq([...r.refs, ...refs]);
  };
  const money = chain?.money ?? [];
  if (money.length) {
    for (const st of money) {
      const m = st.key.match(/^money\.(before|after)\.(.+)$/);
      if (!m || st.kind !== "money") continue;
      const [, side, rest] = m;
      if (side === "before") {
        put(rest, LINE_LABEL[rest] ?? st.label.replace(/^Today: /, ""), "before", V(st.value), st.value.source_refs);
      } else {
        const [head, cid] = rest.split(".");
        if (cid) put(rest, `${names[cid] ?? cid} — ${head === "fixed" ? "plant (capital recovery and O&M, annualised)" : "energy"}`, "after", V(st.value), st.value.source_refs);
        else put(rest, LINE_LABEL[rest] ?? st.label.replace(/^With the plan: /, ""), "after", V(st.value), st.value.source_refs);
      }
    }
  } else {
    const before = s.lines_before ?? {}, after = s.lines_after ?? {};
    for (const k of ["demand", "grid_energy", "excess_demand"]) {
      if (k in before) put(k, LINE_LABEL[k] ?? k, "before", Number(before[k]), []);
      if (k in after) put(k, LINE_LABEL[k] ?? k, "after", Number(after[k]), []);
    }
    for (const k of Object.keys(after).filter((x) => x.includes(":"))) {
      const [head, cid] = k.split(":");
      put(k, `${names[cid] ?? cid} — ${head === "fixed" ? "plant (capital recovery and O&M, annualised)" : "energy"}`, "after", Number(after[k]), []);
    }
  }
  const order = (r: Row) => (r.key === "grid_energy" ? 0 : r.key === "demand" ? 1 : r.key === "excess_demand" ? 2 : 3);
  const shown = rows.filter((r) => !((r.key.startsWith("energy") || r.key.startsWith("fixed")) && !(r.before ?? 0) && !(r.after ?? 0))).sort((a, b) => order(a) - order(b));
  const tb = V(s.annual.before), ta = V(s.annual.after);
  return (
    <div className="ep-scroll">
      <table className="ep-table ep-cost">
        <thead><tr><th>Cost line (year one)</th><th className="num">Today</th><th className="num">With the plan</th><th className="num">Difference</th>{!print && <th>Source</th>}</tr></thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.key}>
              <td>{r.label}</td>
              <td className="num">{r.before === null ? "—" : inr(r.before)}</td>
              <td className="num">{r.after === null ? "—" : inr(r.after)}</td>
              <td className="num">{r.before === null && r.after === null ? "" : signed((r.after ?? 0) - (r.before ?? 0))}</td>
              {!print && <td><RefChips refs={r.refs} max={1} kinds={1} /></td>}
            </tr>
          ))}
          <tr className="ep-total"><td>Total</td><td className="num">{inr(tb)}</td><td className="num">{inr(ta)}</td><td className="num">{signed(ta - tb)}</td>{!print && <td><RefChips refs={uniq([...s.annual.before.source_refs, ...s.annual.after.source_refs])} max={2} kinds={1} /></td>}</tr>
        </tbody>
      </table>
      <p className="eg-muted ep-small">Today&apos;s lines are the tariff applied to your load profile; the plan&apos;s are the re-settled dispatch under the state&apos;s rules. Open-access and exchange energy is at its landed cost, after charges and losses.</p>
    </div>
  );
}

function signed(v: number): string {
  if (Math.abs(v) < 0.5) return "—";
  return v < 0 ? `−${inr(-v)}` : `+${inr(v)}`;
}

// 4. The 25-year view: cash flows year by year, cumulative, and the assumptions behind them.
export function Lifecycle({ lc, years, expanded = false }: { lc: LifecycleOut; years: number; expanded?: boolean }) {
  const [all, setAll] = useState(expanded);
  const rows = all ? lc.years : lc.years.slice(0, 6);
  const capex0 = Number(lc.capex?.value ?? 0);
  const cum = [-capex0, ...lc.years.map((y) => Number(y.cumulative))]; // year 0 is the capital
  const hi = Math.max(...cum, 1), lo = Math.min(...cum, 0);
  const W = 720, H = 200, pad = 70, top = 14, bottom = 18;
  const x = (i: number) => pad + (i / Math.max(1, cum.length - 1)) * (W - pad - 10);
  const y = (v: number) => top + ((hi - v) / (hi - lo)) * (H - top - bottom);
  const pts = cum.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const breakeven = lc.years.findIndex((yr) => Number(yr.cumulative) >= 0);
  return (
    <>
      <div className="ep-kpis ep-kpis--small">
        <div className="eg-stat"><span className="eg-stat__label">Lifecycle cost today</span><span className="eg-stat__value">{inr(lc.pv_bau?.value)}</span><span className="eg-stat__foot">present value, {years} years</span></div>
        <div className="eg-stat"><span className="eg-stat__label">Lifecycle cost with the plan</span><span className="eg-stat__value">{inr(lc.pv_plan?.value)}</span><span className="eg-stat__foot">incl. capital and O&M</span></div>
        <div className="eg-stat"><span className="eg-stat__label">Net present value</span><span className="eg-stat__value">{inr(lc.npv?.value)}</span><span className="eg-stat__foot">at {num(lc.assumptions.discount_pct?.value, 1)}% discount</span></div>
        {lc.capex && Number(lc.capex.value) > 0 && (
          <div className="eg-stat"><span className="eg-stat__label">Payback</span><span className="eg-stat__value">{lc.simple_payback_years ? `${Number(lc.simple_payback_years.value).toFixed(1)} y` : "—"}</span><span className="eg-stat__foot">{lc.discounted_payback_years ? `${Number(lc.discounted_payback_years.value).toFixed(1)} y discounted` : "not within the period, discounted"}{lc.irr_pct ? ` · IRR ${Number(lc.irr_pct.value).toFixed(1)}%` : ""}</span></div>
        )}
      </div>
      <figure className="ep-lcchart" style={{ margin: "8px 0" }}>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Cumulative cash flow" style={{ width: "100%", height: "auto" }}>
          <line x1={pad} x2={W - 10} y1={y(0)} y2={y(0)} stroke="currentColor" strokeOpacity={0.35} />
          <line x1={pad} x2={pad} y1={top} y2={H - bottom} stroke="currentColor" strokeOpacity={0.15} />
          <text x={pad - 6} y={y(hi) + 4} textAnchor="end" fontSize={10} fill="currentColor" opacity={0.7}>{inr(hi)}</text>
          {y(lo) - y(0) > 12 && <text x={pad - 6} y={y(0) + 4} textAnchor="end" fontSize={10} fill="currentColor" opacity={0.7}>0</text>}
          {lo < 0 && <text x={pad - 6} y={y(lo) + 4} textAnchor="end" fontSize={10} fill="currentColor" opacity={0.7}>−{inr(-lo)}</text>}
          <polyline points={pts} fill="none" stroke="var(--eg-success, #2f9e6b)" strokeWidth={2} />
          {cum.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={2} fill="var(--eg-success, #2f9e6b)" />)}
          {breakeven >= 0 && (
            <>
              <line x1={x(breakeven + 1)} x2={x(breakeven + 1)} y1={top} y2={H - bottom} stroke="currentColor" strokeOpacity={0.25} strokeDasharray="3 3" />
              <text x={x(breakeven + 1) + 4} y={top + 10} fontSize={10} fill="currentColor" opacity={0.8}>break-even, year {breakeven + 1}</text>
            </>
          )}
          {[0, ...lc.years.filter((_, i) => i % 5 === 4).map((yr) => yr.year)].map((n, k) => <text key={k} x={x(n)} y={H - 4} fontSize={10} fill="currentColor" opacity={0.6} textAnchor="middle">{n}</text>)}
        </svg>
        <figcaption className="eg-muted ep-small">Cumulative cash flow: the saving each year, less the capital at year 0 and at each replacement.</figcaption>
      </figure>
      <div className="ep-scroll">
        <table className="ep-table ep-small ep-lc">
          <thead><tr><th>Year</th><th className="num">Grid bill today</th><th className="num">Grid with the plan</th><th className="num">Contracted power</th><th className="num">O&M</th><th className="num">Capital</th><th className="num">Saving</th><th className="num">Cumulative</th></tr></thead>
          <tbody>
            {Number(lc.capex?.value ?? 0) > 0 && <tr><td>0</td><td colSpan={4}></td><td className="num">{inr(lc.capex?.value)}</td><td></td><td className="num">−{inr(lc.capex?.value)}</td></tr>}
            {rows.map((yr) => (
              <tr key={yr.year}><td>{yr.year}</td><td className="num">{inr(yr.bau)}</td><td className="num">{inr(yr.grid)}</td><td className="num">{inr(yr.contracted)}</td><td className="num">{inr(yr.om)}</td><td className="num">{Number(yr.capex) ? inr(yr.capex) : ""}</td><td className="num">{inr(yr.saving)}</td><td className="num">{inr(yr.cumulative)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      {lc.years.length > 6 && <button className="ep-link ep-small" onClick={() => setAll(!all)}>{all ? "Show the first six years" : `Show all ${lc.years.length} years`}</button>}
      <p className="eg-muted ep-small">
        Assumptions: tariff escalation {num(lc.assumptions.tariff_escalation_pct?.value, 1)}% a year, PPA escalation {num(lc.assumptions.ppa_escalation_pct?.value, 1)}%, O&M escalation {num(lc.assumptions.om_escalation_pct?.value, 1)}%, discount {num(lc.assumptions.discount_pct?.value, 1)}%.
        {Object.values(lc.assumptions).map((a, i) => <RefChips key={i} refs={a.source_refs} max={1} />)}
        {lc.notes.map((n, i) => <span key={i}> {n}.</span>)}
      </p>
    </>
  );
}

// One colour per source across every chart: by kind where the kind is known, else by position.
const COLORS: Record<string, string> = { grid: "#8b95a3", withdrawn: "#c6e04a", battery: "#3b82f6" };
const KIND_COLORS: Record<string, string> = {
  rooftop_pv: "#f5b544", oa_solar_intra: "#2f9e6b", oa_solar_ists: "#1f7a52", group_captive: "#7fc97f",
  oa_wind_intra: "#4fb3d9", oa_wind_ists: "#2b8a8a", oa_hybrid_intra: "#0ea5a4", oa_hybrid_ists: "#0b7f7e",
  iex_dam: "#c084fc", iex_rtm: "#a855f7", iex_gdam: "#d8b4fe", iex_gtam: "#e9d5ff", iex_tam: "#9333ea", iex_hpdam: "#7e22ce",
};
export function sourceColor(id: string, kind: string | undefined, i: number): string {
  return (kind && KIND_COLORS[kind]) ?? KIND_COLORS[id.split(":")[0]] ?? MIX_COLORS[i % MIX_COLORS.length];
}

// 5. Dispatch explorer: a window of days anywhere in the year.

export function DispatchChart({ d, labels, kinds = {} }: { d: DispatchOut; labels: Record<string, string>; kinds?: Record<string, string> }) {
  const n = d.times.length;
  if (!n) return <p className="eg-muted">No dispatch for these days.</p>;
  const val = (k: string, i: number) => Number(d.series[k]?.[i]?.value ?? 0);
  const perHour = 60 / d.minutes;
  const supply = Object.keys(d.series).filter((k) => k.startsWith("supply:"));
  const discharge = Object.keys(d.series).filter((k) => k.startsWith("discharge:"));
  const layers = [
    ...supply.map((k, j) => ({ key: k, label: labels[k.slice(7)] ?? k.slice(7).replaceAll("_", " "), color: sourceColor(k.slice(7), kinds[k.slice(7)], j), v: (i: number) => val(k, i) })),
    ...(discharge.length ? [{ key: "battery", label: "battery discharge", color: COLORS.battery, v: (i: number) => discharge.reduce((a, k) => a + val(k, i), 0) }] : []),
    { key: "withdrawn", label: "from the bank", color: COLORS.withdrawn, v: (i: number) => val("withdrawn", i) },
    { key: "grid", label: "from the DISCOM", color: COLORS.grid, v: (i: number) => val("grid", i) },
  ];
  const stack = Array.from({ length: n }, (_, i) => layers.map((l) => l.v(i) * perHour));
  const load = Array.from({ length: n }, (_, i) => val("load", i) * perHour);
  const top = Math.max(1, ...load, ...stack.map((s) => s.reduce((a, b) => a + b, 0)));
  const W = 960, H = 280, pad = 44;
  const x = (i: number) => pad + (i / Math.max(1, n - 1)) * (W - pad - 8);
  const y = (v: number) => H - 26 - (v / top) * (H - 44);
  const areas = layers.map((l, li) => {
    const lo = (i: number) => stack[i].slice(0, li).reduce((a, b) => a + b, 0);
    const up = Array.from({ length: n }, (_, i) => `${x(i).toFixed(1)},${y(lo(i) + stack[i][li]).toFixed(1)}`);
    const down = Array.from({ length: n }, (_, i) => `${x(n - 1 - i).toFixed(1)},${y(lo(n - 1 - i)).toFixed(1)}`);
    return { ...l, points: [...up, ...down].join(" ") };
  });
  const loadLine = load.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const perDay = 24 * perHour;
  const days = Array.from({ length: Math.ceil(n / perDay) }, (_, k) => k * perDay).filter((i) => i < n);
  const fmtMw = (v: number) => (top >= 2000 ? `${(v / 1000).toFixed(1)} MW` : `${Math.round(v)} kW`);
  return (
    <figure className="ep-dispatch" style={{ margin: 0 }}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Dispatch" style={{ width: "100%", height: "auto" }}>
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <g key={f}>
            <line x1={pad} x2={W - 8} y1={y(top * f)} y2={y(top * f)} stroke="currentColor" strokeOpacity={0.08} />
            <text x={pad - 4} y={y(top * f) + 4} textAnchor="end" fontSize={10} fill="currentColor" opacity={0.6}>{fmtMw(top * f)}</text>
          </g>
        ))}
        {areas.map((a) => <polygon key={a.key} points={a.points} fill={a.color} fillOpacity={0.75} />)}
        <polyline points={loadLine} fill="none" stroke="currentColor" strokeWidth={1.4} />
        {days.map((i) => <text key={i} x={x(i) + 4} y={H - 8} fontSize={10} fill="currentColor" opacity={0.7}>{new Date(d.times[i]).toLocaleDateString("en-IN", { day: "numeric", month: "short", weekday: n <= 7 * perDay ? "short" : undefined })}</text>)}
      </svg>
      <figcaption className="ep-legend ep-small">
        <span><span style={{ display: "inline-block", width: 14, borderTop: "2px solid currentColor", verticalAlign: "middle" }} /> load</span>
        {layers.map((l) => <span key={l.key}><span style={{ display: "inline-block", width: 10, height: 10, background: l.color, borderRadius: 2, verticalAlign: "middle", marginRight: 4 }} />{l.label}</span>)}
      </figcaption>
    </figure>
  );
}

// 6. The year month by month.
export function YearMix({ months, sizes }: { months: MonthMix[]; sizes: SizeOut[] }) {
  const label = Object.fromEntries(sizes.map((z) => [z.id, z.label]));
  const kind = Object.fromEntries(sizes.map((z) => [z.id, z.kind]));
  const ids = [...new Set(months.flatMap((m) => Object.keys(m.sources)))].filter((id) => months.some((m) => V(m.sources[id]) > 0));
  const layers = [
    ...ids.map((id, i) => ({ key: id, label: label[id] ?? id, color: kind[id] === "btm_bess" ? COLORS.battery : sourceColor(id, kind[id], i), v: (m: MonthMix) => V(m.sources[id]) })),
    { key: "bank", label: "From the bank", color: COLORS.withdrawn, v: (m: MonthMix) => V(m.withdrawn_kwh) },
    { key: "grid", label: "From the DISCOM", color: COLORS.grid, v: (m: MonthMix) => V(m.grid_kwh) },
  ];
  const max = Math.max(...months.map((m) => V(m.load_kwh)), 1);
  const total = (f: (m: MonthMix) => number) => months.reduce((a, m) => a + f(m), 0);
  const load = total((m) => V(m.load_kwh));
  return (
    <>
      <div className="ep-yearmix" role="img" aria-label="Monthly energy mix">
        {months.map((m) => (
          <div key={m.month} className="ep-yearmix__col">
            <div className="ep-yearmix__bar" style={{ height: `${(V(m.load_kwh) / max) * 100}%` }}>
              {layers.map((l) => { const v = l.v(m); return v > 0 ? <span key={l.key} title={`${l.label}: ${(v / 1000).toFixed(0)} MWh`} style={{ flexGrow: v, background: l.color }} /> : null; })}
            </div>
            <span className="ep-small eg-muted">{new Date(m.month).toLocaleString("en-IN", { month: "short" })}</span>
          </div>
        ))}
      </div>
      <div className="ep-legend ep-small">
        {layers.map((l) => <span key={l.key}><span style={{ display: "inline-block", width: 10, height: 10, background: l.color, borderRadius: 2, marginRight: 4 }} />{l.label} · {num(total(l.v) / 1000)} MWh ({load > 0 ? ((total(l.v) / load) * 100).toFixed(1) : "0"}%)</span>)}
      </div>
    </>
  );
}

// 7. Settlement, emissions, constraints, inputs.
export function Settlement({ s, chain }: { s: SummaryOut; chain: Chain | null }) {
  const load = s.monthly?.reduce((a, m) => a + V(m.load_kwh), 0) ?? 0;
  return (
    <div className="ep-grid2">
      <div>
        <h3 className="eg-overline">Banking and settlement</h3>
        <table className="ep-table ep-small"><tbody>
          <tr><td>Rule applied</td><td>{chain?.settlement_rule ?? s.settlement.rule ?? "none approved for this state"} {chain?.settlement_ref && <RefChips refs={[chain.settlement_ref]} max={1} />}</td></tr>
          <tr><td>Consumption for the year</td><td className="num">{num(load / 1000)} MWh</td></tr>
          <tr><td>Drawn from the DISCOM with the plan</td><td className="num">{num(V(s.settlement.grid_kwh) / 1000)} MWh</td></tr>
          <tr><td>Withdrawn from the bank</td><td className="num">{num(V(s.settlement.withdrawn_kwh) / 1000)} MWh</td></tr>
          <tr><td>Banked but lapsed</td><td className="num">{num(V(s.settlement.lapsed_kwh) / 1000)} MWh</td></tr>
          <tr><td>Contract demand kept</td><td className="num">{num(s.contract_demand_kva.value)} kVA</td></tr>
        </tbody></table>
      </div>
      <div>
        <h3 className="eg-overline">Emissions</h3>
        <table className="ep-table ep-small"><tbody>
          <tr><td>Grid CO₂ today</td><td className="num">{num(V(s.emissions.before_t))} t a year</td></tr>
          <tr><td>Grid CO₂ with the plan</td><td className="num">{num(V(s.emissions.after_t))} t a year</td></tr>
          <tr><td>Avoided</td><td className="num"><b>{num(V(s.emissions.before_t) - V(s.emissions.after_t))} t</b></td></tr>
          <tr><td>Grid factor</td><td className="num">{Number(s.emissions.factor.value).toFixed(3)} tCO₂/MWh <RefChips refs={uniq(s.emissions.factor.source_refs)} max={1} /></td></tr>
        </tbody></table>
      </div>
    </div>
  );
}

export function Constraints({ s }: { s: SummaryOut }) {
  return (
    <>
      {s.binding.length === 0 ? <p className="eg-muted ep-small">Nothing binds: the sizes are where the money says.</p> : (
        <ul className="ep-list">{s.binding.map((b) => <li key={b.name}>{b.words} <RefChips refs={uniq(b.refs.flatMap((r) => r.source_refs))} max={3} /></li>)}</ul>
      )}
      {s.sensitivities.length > 0 && (
        <>
          <h3 className="eg-overline" style={{ marginTop: 12 }}>If prices move</h3>
          <table className="ep-table ep-small"><tbody>{s.sensitivities.map((x) => <tr key={x.label}><td>{x.label}</td><td className="num">{inr(x.saving.value)} a year</td></tr>)}</tbody></table>
        </>
      )}
    </>
  );
}

export function Inputs({ run, chain }: { run: RunOut; chain: Chain | null }) {
  const s = run.summary!;
  const gaps = useMemo(() => {
    const out = new Map<string, string[]>();
    for (const src of chain?.sources ?? []) for (const g of Object.values(src.gaps)) out.set(g, [...(out.get(g) ?? []), src.label]);
    return [...out.entries()];
  }, [chain]);
  return (
    <div className="ep-grid2">
      <div>
        <h3 className="eg-overline">Inputs</h3>
        <ul className="ep-list ep-small">
          <li>Load profile: {s.provenance.load_profile} <RefChips refs={s.provenance.profile_ref.source_refs} max={1} /></li>
          {s.provenance.prices.length > 0 && <li>Exchange prices: IEX vintages {s.provenance.prices.join(", ")}</li>}
          <li>Resolution: {run.resolution_min === 60 ? "hourly (8,760 blocks)" : "15 minutes (35,040 blocks)"}; solver {run.solver.status ?? "—"}{run.solver.seconds ? ` in ${Math.round(run.solver.seconds)} s` : ""}{run.solver.gap !== undefined && run.solver.gap !== null ? `, gap ${(Number(run.solver.gap) * 100).toFixed(2)}%` : ""}</li>
          <li>Settled {run.finished_at ? new Date(run.finished_at).toLocaleString("en-IN") : ""}; run {run.id.slice(0, 8)} is reproducible from its pinned rules, prices and profile.</li>
          {s.notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      </div>
      <div>
        <h3 className="eg-overline">Not yet sourced</h3>
        {gaps.length === 0 ? <p className="eg-muted ep-small">Every component of every source has a regulation page behind it.</p> : (
          <ul className="ep-list ep-small">{gaps.map(([g, srcs]) => <li key={g}>{g} <span className="eg-muted">({srcs.join(", ")})</span></li>)}</ul>
        )}
      </div>
    </div>
  );
}
