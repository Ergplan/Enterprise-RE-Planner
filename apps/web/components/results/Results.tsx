"use client";

import Link from "next/link";
import { RefChips } from "@/components/cost/RefChips";
import { useCallback, useEffect, useMemo, useState } from "react";
import { WhatIf } from "@/components/plan/WhatIf";
import type { Chain } from "@/lib/audit";
import { inr } from "@/lib/evaluate";
import { clientFetch, type ConnectionOut } from "@/lib/intake";
import type { PlanOut } from "@/lib/plan";
import type { DispatchOut, RunOut, ScenarioOut } from "@/lib/runs";
import { Constraints, CostTable, DispatchChart, Inputs, Lifecycle, Settlement, Sizes, Summary, YearMix } from "./parts";

type ShareOut = { token: string; path: string; url: string };

// The results: one scenario's settled year and 25-year view, every section of the report on one page,
// with the other scenarios a tab away. Polls while a run is queued or running.
function fmtUnit(v?: string, u?: string): string {
  if (v === undefined || v === null) return "";
  const n = Number(v);
  const txt = Number.isFinite(n) ? n.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : String(v);
  const unit = (u ?? "").replace(/^INR/, "₹").replace("percent", "%").replace("tCO2", "tCO₂").replace("count", "");
  return unit === "%" ? `${txt}%` : unit ? `${txt} ${unit}` : txt;
}

export function Results({ connectionId, scenarioId }: { connectionId: string; scenarioId: string | null }) {
  const [conn, setConn] = useState<ConnectionOut | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioOut[]>([]);
  const [current, setCurrent] = useState<string | null>(scenarioId);
  const [chain, setChain] = useState<Chain | null>(null);
  const [plan, setPlan] = useState<PlanOut | null>(null);
  const [share, setShare] = useState<ShareOut | null>(null);
  const [error, setError] = useState("");
  const [section, setSection] = useState<string>("");

  const load = useCallback(async () => {
    try {
      const c = conn ?? (await clientFetch<ConnectionOut>(`/connections/${connectionId}`));
      if (!conn) setConn(c);
      const sc = await clientFetch<ScenarioOut[]>(`/sites/${c.site.id}/scenarios`);
      const mine = sc.filter((x) => x.connection_id === connectionId);
      setScenarios(mine);
      if (!current) {
        const best = mine.filter((x) => x.latest_run?.status === "done").sort((a, b) => Number(b.latest_run!.summary!.annual.saving.value) - Number(a.latest_run!.summary!.annual.saving.value))[0] ?? mine[0];
        if (best) setCurrent(best.id);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }, [connectionId, conn, current]);

  useEffect(() => { void load(); }, [load]);

  const scenario = scenarios.find((s) => s.id === current) ?? null;
  const run: RunOut | null = scenario?.latest_run ?? null;
  const settling = !!run && (run.status === "queued" || run.status === "running");
  const anyPending = scenarios.some((s) => !s.latest_run || s.latest_run.status === "queued" || s.latest_run.status === "running");

  // poll while anything is still settling
  useEffect(() => {
    if (!anyPending) return;
    const t = setInterval(() => void load(), 5000);
    return () => clearInterval(t);
  }, [anyPending, load]);

  // the chain (landed cost per source, settlement rule) and the plan (documents, editable values) for the chosen scenario
  useEffect(() => {
    if (!run || run.status !== "done") { setChain(null); return; }
    clientFetch<Chain>(`/connections/${connectionId}/chain?scenario_id=${current}`).then(setChain).catch(() => setChain(null));
    clientFetch<PlanOut>(`/connections/${connectionId}/plan`).then(setPlan).catch(() => setPlan(null));
  }, [connectionId, current, run?.id, run?.status]);

  async function makeShare(): Promise<ShareOut | null> {
    try {
      const out = await clientFetch<ShareOut>(`/connections/${connectionId}/share`, { method: "POST" });
      setShare(out);
      return out;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  }

  const years = run?.summary?.lifecycle ? Number(run.summary.lifecycle.analysis_years.value) : 25;
  const labels = useMemo(() => Object.fromEntries((run?.summary?.sizes ?? []).map((z) => [z.id, z.label])), [run?.summary?.sizes]);
  const TOC = [
    ["summary", "Summary"], ["system", "Recommended system"], ["cost", "Cost comparison"], ["lifecycle", `${years}-year view`],
    ["dispatch", "Dispatch"], ["year", "Month by month"], ["settlement", "Settlement and emissions"], ["why", "What holds it"], ["inputs", "Inputs and sources"], ["next", "Share, audit, download"],
  ];

  if (error && !conn) return <p className="ep-error">{error}</p>;
  return (
    <div className="ep-res">
      <aside className="ep-res__rail">
        {conn && (
          <div className="ep-res__site">
            <b>{conn.client.name}</b>
            <div className="eg-muted ep-small">{conn.site.name} · {conn.discom_id.toUpperCase()}{conn.site.state ? `, ${conn.site.state}` : ""}</div>
            <div className="eg-muted ep-small">{conn.tariff_category ?? ""}{conn.contract_demand_kva ? ` · ${Number(conn.contract_demand_kva).toLocaleString("en-IN")} kVA` : ""}</div>
          </div>
        )}
        <nav className="ep-toc" aria-label="Sections">
          {TOC.map(([id, label]) => <a key={id} href={`#${id}`} aria-current={section === id ? "true" : undefined} onClick={() => setSection(id)}>{label}</a>)}
        </nav>
        <div className="ep-rail__actions">
          <Link className="eg-btn eg-btn--ghost eg-btn--block" href={`/evaluate?c=${connectionId}`}>Change the inputs</Link>
        </div>
      </aside>

      <div className="ep-res__main">
        {scenarios.length > 0 && (
          <div className="ep-tabs" role="tablist" aria-label="Scenarios">
            {scenarios.map((s) => {
              const r = s.latest_run;
              const st = r?.status ?? "none";
              return (
                <button key={s.id} role="tab" aria-selected={s.id === current} className={`ep-tab${s.id === current ? " ep-tab--on" : ""}`} onClick={() => setCurrent(s.id)}>
                  <span>{s.name}</span>
                  <span className="eg-muted ep-small">{st === "done" ? `${inr(r!.summary!.annual.saving.value)} a year` : st === "queued" || st === "running" ? "sizing…" : st.replace("_", " ")}</span>
                </button>
              );
            })}
          </div>
        )}
        {error && <p className="ep-error">{error}</p>}
        {!run && scenarios.length === 0 && <section className="eg-card ep-panel"><p className="eg-muted">Nothing sized yet for this site. <Link href={`/evaluate?c=${connectionId}`}>Choose what to evaluate</Link> and get results.</p></section>}
        {run && settling && (
          <section className="eg-card ep-panel ep-settling">
            <span className="eg-dot eg-dot--live"></span>
            <div>
              <b>Sizing {scenario?.name}…</b>
              <p className="eg-muted ep-small">The optimizer is finding the least-cost size of each source over the year ({run.resolution_min === 60 ? "8,760 hourly blocks" : "35,040 fifteen-minute blocks"}), then re-settling the dispatch under the state&apos;s rules. About a minute hourly; several at 15 minutes. This page refreshes itself.</p>
            </div>
          </section>
        )}
        {run && (run.status === "failed" || run.status === "failed_resettle") && (
          <section className="eg-card ep-panel"><p className="ep-error">This scenario did not settle: {run.error ?? run.status.replace("_", " ")}. Change the inputs and try again, or ask jouleWise.</p></section>
        )}

        {run?.summary && run.status === "done" && (
          <>
            <section id="summary" className="eg-card ep-panel ep-report">
              <h2 className="eg-card__title">Summary</h2>
              <p className="eg-card__sub">{scenario?.name}: the least-cost mix of the sources you chose, sized over a {run.resolution_min === 60 ? "hourly" : "15-minute"} year and re-settled under {chain?.settlement_rule ? `“${chain.settlement_rule}”` : "the state's rules"}, then projected {years} years.</p>
              <Summary s={run.summary} years={years} />
            </section>

            <section id="system" className="eg-card ep-panel ep-report">
              <h2 className="eg-card__title">Recommended system</h2>
              <p className="eg-card__sub">What to build or contract, how much energy each source brings to your meter in a year, and what a unit of it costs there after charges and losses.</p>
              <Sizes s={run.summary} chain={chain} />
              {chain && chain.sources.some((x) => x.landed.length) && (
                <p className="ep-small"><Link href={`/plan/audit?c=${connectionId}&s=${current}`}>See the full chain of charges and losses behind each landed cost →</Link></p>
              )}
            </section>

            <section id="cost" className="eg-card ep-panel ep-report">
              <h2 className="eg-card__title">Cost comparison, year one</h2>
              <CostTable s={run.summary} chain={chain} />
            </section>

            {run.summary.lifecycle && (
              <section id="lifecycle" className="eg-card ep-panel ep-report">
                <h2 className="eg-card__title">{years}-year view</h2>
                <p className="eg-card__sub">The settled year projected forward: the DISCOM&apos;s tariff escalating, contracted power at its own rate, owned plant paid up front and replaced when its life ends, output degrading, every year brought to today&apos;s money.</p>
                <Lifecycle lc={run.summary.lifecycle} years={years} />
              </section>
            )}

            <section id="dispatch" className="eg-card ep-panel ep-report">
              <h2 className="eg-card__title">Dispatch</h2>
              <p className="eg-card__sub">How the load is met block by block in the settled year: each source under the load line, then the bank, then the DISCOM.</p>
              <DispatchExplorer runId={run.id} labels={labels} kinds={Object.fromEntries(run.summary.sizes.map((z) => [z.id, z.kind]))} minutes={run.resolution_min} />
            </section>

            {run.summary.monthly && run.summary.monthly.length > 0 && (
              <section id="year" className="eg-card ep-panel ep-report">
                <h2 className="eg-card__title">Your year, month by month</h2>
                <p className="eg-card__sub">Where each month&apos;s consumption comes from once the year is settled under the state&apos;s rules.</p>
                <YearMix months={run.summary.monthly} sizes={run.summary.sizes} />
              </section>
            )}

            <section id="settlement" className="eg-card ep-panel ep-report">
              <h2 className="eg-card__title">Settlement and emissions</h2>
              <Settlement s={run.summary} chain={chain} />
            </section>

            <section id="why" className="eg-card ep-panel ep-report">
              <h2 className="eg-card__title">What holds this answer where it is</h2>
              <Constraints s={run.summary} />
            </section>

            <section id="inputs" className="eg-card ep-panel ep-report">
              <h2 className="eg-card__title">Inputs, assumptions and sources</h2>
              <Inputs run={run} chain={chain} />
              {plan && plan.assumptions.length > 0 && (
                <>
                  <h3 className="eg-overline" style={{ marginTop: 12 }}>Assumptions you can correct</h3>
                  <ul className="ep-list ep-small">
                    {plan.assumptions.map((a, i) => (
                      <li key={i}>{a.label ? <><b>{a.label}</b>: {fmtUnit(a.value, a.unit)} — </> : null}{a.note} <RefChips refs={[a.ref]} max={0} /></li>
                    ))}
                  </ul>
                </>
              )}
              {plan && plan.documents.length > 0 && (
                <>
                  <h3 className="eg-overline" style={{ marginTop: 12 }}>Regulations and orders cited</h3>
                  <ul className="ep-list ep-small">
                    {plan.documents.map((d) => <li key={d.id}><a href={d.url} target="_blank" rel="noreferrer">{d.title}</a>{d.regulator ? ` — ${d.regulator}` : ""}{d.pages.length ? ` · pages ${d.pages.slice(0, 8).join(", ")}${d.pages.length > 8 ? "…" : ""}` : ""}{d.url_public ? <> · <a href={d.url_public} target="_blank" rel="noreferrer">regulator&apos;s copy</a></> : null}</li>)}
                  </ul>
                </>
              )}
            </section>

            <section id="next" className="eg-card ep-panel ep-report">
              <h2 className="eg-card__title">Share, audit, download</h2>
              <div className="ep-next">
                <div>
                  <h3 className="eg-overline">Share the plan</h3>
                  <p className="eg-muted ep-small">A live link that opens without sign-in, with every scenario, the chain of charges, and a voice what-if; the same page prints to PDF with citations as numbered notes.</p>
                  <div className="ep-row">
                    <button className="eg-btn eg-btn--primary eg-btn--sm" onClick={() => void makeShare()}>{share ? "Link ready" : "Create a share link"}</button>
                    {share && <a className="eg-btn eg-btn--ghost eg-btn--sm" href={`/api/p/${share.token}/pdf`} target="_blank" rel="noreferrer"><span data-icon="download" data-size="14"></span> PDF report</a>}
                  </div>
                  {share && <a className="ep-share-link" href={share.path}>{share.url}</a>}
                </div>
                <div>
                  <h3 className="eg-overline">Check the figures</h3>
                  <ul className="ep-list ep-small">
                    <li><Link href={`/plan/audit?c=${connectionId}&s=${current}`}>Audit the chain</Link>: every charge, loss and exemption with its page; upload your own working and compare.</li>
                    <li><Link href={`/plan/today?c=${connectionId}`}>Today&apos;s bill rebuilt</Link> line by line from the tariff order.</li>
                    <li><Link href={`/plan/landed?c=${connectionId}`}>Landed cost per time-of-day slot</Link> for every source.</li>
                  </ul>
                </div>
                <div>
                  <h3 className="eg-overline">Download</h3>
                  <ul className="ep-list ep-small">
                    <li><a href={`/api/runs/${run.id}/dispatch.csv`}>The settled year, every block (CSV)</a></li>
                    <li><a href={`/api/connections/${connectionId}/profile.csv`}>Your load profile, 35,040 blocks (CSV)</a></li>
                  </ul>
                </div>
              </div>
              {share && plan && plan.editable.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <h3 className="eg-overline">What if</h3>
                  <WhatIf token={share.token} editable={plan.editable} />
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function DispatchExplorer({ runId, labels, kinds, minutes }: { runId: string; labels: Record<string, string>; kinds: Record<string, string>; minutes: number }) {
  const [start, setStart] = useState<string | null>(null); // null: the busiest week
  const [days, setDays] = useState(7);
  const [d, setD] = useState<DispatchOut | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const q = new URLSearchParams({ days: String(days) });
    if (start) q.set("start", start);
    clientFetch<DispatchOut>(`/runs/${runId}/dispatch?${q}`).then((x) => { setD(x); setError(""); }).catch((e) => setError((e as Error).message));
  }, [runId, start, days]);
  const shift = (n: number) => {
    const base = start ?? d?.start;
    if (!base) return;
    const t = new Date(base);
    t.setDate(t.getDate() + n);
    setStart(t.toISOString().slice(0, 10));
  };
  const months = Array.from({ length: 12 }, (_, i) => i);
  const year = d ? new Date(d.start).getFullYear() : new Date().getFullYear();
  return (
    <>
      <div className="ep-row ep-dispatch__ctl">
        <div className="eg-seg eg-seg--sm" role="group" aria-label="Window">
          {[1, 3, 7, 14].map((n) => <button key={n} aria-pressed={days === n} onClick={() => setDays(n)}>{n === 1 ? "A day" : `${n} days`}</button>)}
        </div>
        <button className="eg-btn eg-btn--ghost eg-btn--sm" onClick={() => shift(-days)} aria-label="Earlier">‹</button>
        <span className="eg-input"><select aria-label="Month" value={d ? d.start.slice(0, 7) : ""} onChange={(e) => setStart(`${e.target.value}-01`)}>
          {months.map((m) => { const dt = new Date(year, m, 1); const key = `${dt.getFullYear()}-${String(m + 1).padStart(2, "0")}`; return <option key={key} value={key}>{dt.toLocaleString("en-IN", { month: "long", year: "numeric" })}</option>; })}
        </select></span>
        <button className="eg-btn eg-btn--ghost eg-btn--sm" onClick={() => shift(days)} aria-label="Later">›</button>
        <button className="eg-btn eg-btn--ghost eg-btn--sm" onClick={() => setStart(null)}>Busiest week</button>
        <span className="eg-muted ep-small">{d ? `from ${new Date(d.start).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}, ${minutes}-minute blocks` : ""}</span>
      </div>
      {error && <p className="ep-error">{error}</p>}
      {d && <DispatchChart d={d} labels={labels} kinds={kinds} />}
    </>
  );
}
