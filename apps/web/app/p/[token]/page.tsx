import type { ReactNode } from "react";
import { RefChips } from "@/components/cost/RefChips";
import { AnalystView } from "@/components/plan/AnalystView";
import { Explain } from "@/components/plan/Explain";
import { WhatIf } from "@/components/plan/WhatIf";
import { VoicePanel } from "@/components/voice/VoicePanel";
import { apiOrNull } from "@/lib/api";
import { uniqueRefs } from "@/lib/cost";
import type { Ref, SourcedValue } from "@/lib/intake";
import { Citations, type PlanOut } from "@/lib/plan";
import { crore, mw, mwh } from "@/lib/runs";

export const metadata = { title: "Your green power plan · jouleWise" };

// The live plan: shared by token, readable logged out. ?print=1 is the layout Chromium prints to PDF —
// citations become numbered footnotes and the documents an appendix.
export default async function LivePlan({ params, searchParams }: { params: Promise<{ token: string }>; searchParams: Promise<{ print?: string }> }) {
  const { token } = await params;
  const { print } = await searchParams;
  const d = await apiOrNull<PlanOut>(`/p/${token}`);
  if (!d) {
    return (
      <section className="eg-card ep-panel ep-public__inner">
        <h1 className="eg-h1">This link does not open a plan</h1>
        <p className="eg-muted">It may have been withdrawn. Ask jouleWise for a new one.</p>
      </section>
    );
  }
  const printing = print === "1";
  const cites = new Citations();
  // called as a function (not a component) so the notes are numbered while the page is built
  const C = (v: (SourcedValue | null | undefined)[], max = 3): ReactNode => {
    const refs: Ref[] = uniqueRefs(v);
    if (printing) {
      const n = cites.cite(refs);
      const other = refs
        .filter((r) => r.kind === "assumption" || r.kind === "client_stated" || r.kind === "bill")
        .map((r) => (r.kind === "assumption" ? "assumed" : r.kind === "client_stated" ? "you said" : "your bill"));
      return <sup className="ep-cite-n">{[ranges(n), ...new Set(other)].filter(Boolean).join(", ")}</sup>;
    }
    return <RefChips refs={refs} max={max} />;
  };
  const rec = d.scenarios.find((s) => s.scenario_id === d.recommended) ?? null;
  const s = rec?.summary;
  return (
    <div className={`ep-public__inner${printing ? " ep-print" : ""}`}>
      {printing && <script dangerouslySetInnerHTML={{ __html: "document.documentElement.dataset.theme='light'" }} />}
      <header className="ep-row" style={{ justifyContent: "space-between" }}>
        <span className="eg-wordmark">erg<i>PLAN</i> <span className="eg-muted ep-small">by jouleWise</span></span>
        {!printing && <a className="eg-btn eg-btn--ghost eg-btn--sm ep-noprint" href={`/api/p/${token}/pdf`} target="_blank" rel="noreferrer">Download PDF</a>}
      </header>
      <div>
        <div className="eg-overline">Green power plan</div>
        <h1 className="eg-h1">{d.client}</h1>
        <p className="eg-muted ep-lede">
          {d.site}, {d.state} · {d.discom.toUpperCase()} · {d.category} · {d.voltage_kv ? `${Number(d.voltage_kv)} kV` : ""} · load profile {d.profile}.
          Every number below is settled under the regulator&apos;s rules and cites the page of the order it comes from{printing ? " (notes at the end)" : "; assumptions are marked and you can change them"}.
        </p>
      </div>
      {!s && <section className="eg-card ep-panel"><p>{d.pending_runs ? `Your plan is being worked out (${d.pending_runs} scenario${d.pending_runs > 1 ? "s" : ""} still settling). This page fills in when they finish.` : "No settled plan yet."}</p></section>}
      {rec && s && (
        <>
          <section className="eg-glass ep-panel">
            <div className="eg-overline">Recommended: {rec.name}</div>
            <div className="ep-big num">{crore(s.annual.saving)} a year {C([s.annual.saving])}</div>
            <p className="ep-small eg-muted">Grid cost today {crore(s.annual.before)} {C([s.annual.before], 2)} → with the plan {crore(s.annual.after)} {C([s.annual.after], 2)}</p>
            <table className="ep-table">
              <tbody>
                {s.sizes.map((z) => (
                  <tr key={z.id}><td>{z.label}{z.exchange && <div className="ep-small eg-muted">bought in {Number(z.exchange.hours_bought).toLocaleString("en-IN")} hours at ₹{Number(z.exchange.avg_landed.value).toFixed(2)}/kWh landed · {Number(z.exchange.share_of_load.value).toFixed(1)}% of your use</div>}</td><td className="num">{z.kind === "btm_bess" ? `${mw(z.kw)} MW / ${mw(z.kwh)} MWh` : z.exchange ? `${mwh(z.delivered_kwh)} MWh · up to ${mw(z.kw)} MW` : `${mw(z.kw)} MW`}</td><td>{C(z.exchange ? [z.delivered_kwh, z.exchange.avg_landed] : [z.kw], 2)}</td></tr>
                ))}
                <tr><td>Payback</td><td className="num">{s.payback_years ? `${Number(s.payback_years.value).toFixed(1)} years` : "—"}</td><td>{s.payback_years && C([s.payback_years], 1)}</td></tr>
                <tr><td>IRR</td><td className="num">{s.irr_pct ? `${Number(s.irr_pct.value).toFixed(1)}%` : "—"}</td><td /></tr>
                <tr><td>Grid CO₂ a year</td><td className="num">{Math.round(Number(s.emissions.before_t.value)).toLocaleString("en-IN")} → {Math.round(Number(s.emissions.after_t.value)).toLocaleString("en-IN")} t</td><td>{C([s.emissions.factor], 1)}</td></tr>
              </tbody>
            </table>
            {s.notes.map((n) => <p key={n} className="eg-muted ep-small">{n}</p>)}
            {s.sizes.some((z) => z.gaps.length > 0) && (
              <p className="ep-small"><span className="eg-chip eg-chip--warning">not yet sourced</span> {[...new Set(s.sizes.flatMap((z) => z.gaps))].join(", ").replaceAll("_", " ")} — these charges are left out until the order or regulation is read, so the saving may be overstated.</p>
            )}
          </section>

          <section className="eg-card ep-panel">
            <h2 className="eg-card__title">The options we compared</h2>
            <table className="ep-table">
              <thead><tr><th>Option</th><th>What it builds or buys</th><th className="num">Saving a year</th><th className="num">Cost with the plan</th></tr></thead>
              <tbody>
                {d.scenarios.map((x) => (
                  <tr key={x.scenario_id}>
                    <td>{x.name}{x.scenario_id === d.recommended ? " (recommended)" : ""}</td>
                    <td className="ep-small">{x.summary.sizes.map((z) => `${z.label} ${z.kind === "btm_bess" ? `${mw(z.kw)} MW/${mw(z.kwh)} MWh` : z.exchange ? `${mwh(z.delivered_kwh)} MWh bought` : `${mw(z.kw)} MW`}`).join(" · ")}</td>
                    <td className="num">{crore(x.summary.annual.saving)} {C([x.summary.annual.saving], 1)}</td>
                    <td className="num">{crore(x.summary.annual.after)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="eg-card ep-panel">
            <h2 className="eg-card__title">How each source adds up at your meter</h2>
            {s.sizes.filter((z) => Object.keys(z.waterfall).length).map((z) => {
              const [slot, lines] = Object.entries(z.waterfall)[0];
              return (
                <div key={z.id} style={{ marginBottom: 16 }}>
                  <div className="eg-overline">{z.label} · {slot}</div>
                  <table className="ep-table ep-small"><tbody>
                    {lines.map((l, i) => <tr key={i}><td>{l.label}</td><td className="num">₹{Number(l.value).toFixed(4)}/kWh</td><td>{C([l], 2)}</td></tr>)}
                  </tbody></table>
                  {!printing && d.token && <Explain token={d.token} scenarioId={rec.scenario_id} item={`waterfall:${z.id}`} />}
                </div>
              );
            })}
          </section>

          <section className="eg-card ep-panel">
            <h2 className="eg-card__title">What holds the answer where it is</h2>
            {s.binding.length === 0 && <p className="eg-muted ep-small">Nothing binds: the sizes are where the money says.</p>}
            <ul className="ep-list">
              {s.binding.map((b) => (
                <li key={b.name}>{b.words} {C(b.refs, 3)}{!printing && d.token && <> <Explain token={d.token} scenarioId={rec.scenario_id} item={`binding:${b.name}`} /></>}</li>
              ))}
            </ul>
          </section>

          {!printing && d.token && (
            <section className="eg-card ep-panel ep-noprint">
              <h2 className="eg-card__title">What if?</h2>
              <p className="eg-card__sub">Change an assumption, or ask by voice or text: a price, a capacity, your contract demand, switching a source off, or the rules on another date.</p>
              <WhatIf token={d.token} editable={d.editable} />
              <div style={{ marginTop: 16 }}>
                <VoicePanel mode="plan" token={d.token} intro="Ask a what-if: a price, a capacity, your contract demand, or switching a source off." />
              </div>
            </section>
          )}
          {!printing && d.token && <AnalystView token={d.token} />}
        </>
      )}

      {printing && cites.notes.length > 0 && (
        <section className="ep-panel">
          <h2 className="eg-card__title">Notes</h2>
          <ol className="ep-small">
            {cites.notes.map((r, i) => {
              const doc = d.documents.find((x) => x.id === r.document_id);
              return <li key={i}>{doc?.title ?? r.document_id}, page {r.page}{r.quote ? `: “${r.quote.slice(0, 220)}${r.quote.length > 220 ? "…" : ""}”` : ""}</li>;
            })}
          </ol>
        </section>
      )}
      <section className="ep-panel">
        <h2 className="eg-card__title">Documents this plan cites</h2>
        <ul className="ep-list ep-small">
          {d.documents.map((doc) => (
            <li key={doc.id}>
              {doc.title}{doc.regulator ? ` (${doc.regulator})` : ""} — pages {doc.pages.join(", ")}.{" "}
              {!printing && <a href={`/api${doc.url}#page=${doc.pages[0] ?? 1}`} target="_blank" rel="noreferrer">Open the stored copy</a>}
              {doc.url_public && <> · <a href={doc.url_public} target="_blank" rel="noreferrer">{printing ? doc.url_public : "regulator's link"}</a></>}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function ranges(n: number[]): string {
  const xs = [...n].sort((a, b) => a - b);
  const out: string[] = [];
  for (let i = 0; i < xs.length; i++) {
    let j = i;
    while (j + 1 < xs.length && xs[j + 1] === xs[j] + 1) j++;
    out.push(j > i ? `${xs[i]}–${xs[j]}` : String(xs[i]));
    i = j;
  }
  return out.join(", ");
}
