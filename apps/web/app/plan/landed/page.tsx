import Link from "next/link";
import { CompareBars } from "@/components/cost/CompareBars";
import { SourceCard } from "@/components/cost/SourceCard";
import { apiOrNull } from "@/lib/api";
import type { LandedOut } from "@/lib/cost";
import type { ConnectionOut } from "@/lib/intake";

// Journey step 3: the landed cost of every source at the meter, per ToD slot, with each line's citation.
// `?view=analyst` shows the rule rows behind each card (the jouleWise view).
export default async function LandedPage({ searchParams }: { searchParams: Promise<{ c?: string; view?: string; month?: string }> }) {
  const { c, view, month } = await searchParams;
  if (!c) {
    return (
      <section className="eg-card ep-panel">
        <h1 className="eg-h1">Landed costs</h1>
        <p className="eg-muted">Start with your bill; this step opens once a site exists.</p>
        <Link className="eg-btn eg-btn--primary" href="/plan/intake">Drop a bill</Link>
      </section>
    );
  }
  const scenario = month ? `?scenario=${encodeURIComponent(JSON.stringify({ month: Number(month) }))}` : "";
  const [conn, d] = await Promise.all([apiOrNull<ConnectionOut>(`/connections/${c}`), apiOrNull<LandedOut>(`/connections/${c}/landed-cost${scenario}`)]);
  if (!conn || !d) return <p className="ep-empty">This site was not found.</p>;
  const avoided = Object.fromEntries(d.avoided.map((a) => [a.slot, Number(a.rate.value)]));
  const analyst = view === "analyst";
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return (
    <>
      <div>
        <div className="eg-overline">Step 3 of 6</div>
        <h1 className="eg-h1">Landed costs</h1>
        <p className="eg-muted ep-lede">
          What each source costs at your meter ({conn.discom_id.toUpperCase()}, {conn.tariff_category}, {Number(conn.voltage_kv)} kV), under the rules in force on {d.as_of}, for {months[d.month - 1]}.
          Prices you have not given are assumptions; change them and every line follows.
        </p>
        <div className="ep-row" style={{ marginTop: "var(--space-3)" }}>
          <div className="eg-seg eg-seg--sm" role="group" aria-label="Month">
            {[4, 7, 10, 1].map((m) => (
              <Link key={m} href={`/plan/landed?c=${c}&month=${m}${analyst ? "&view=analyst" : ""}`} className="ep-seglink" aria-current={d.month === m ? "true" : undefined}>{months[m - 1]}</Link>
            ))}
          </div>
          <Link className="eg-btn eg-btn--primary eg-btn--sm" href={`/plan/optimise?c=${c}`}>Size the plan</Link>
          <Link className="eg-btn eg-btn--ghost eg-btn--sm" href={`/plan/landed?c=${c}${month ? `&month=${month}` : ""}${analyst ? "" : "&view=analyst"}`}>
            {analyst ? "Client view" : "jouleWise view"}
          </Link>
          <Link className="eg-btn eg-btn--ghost eg-btn--sm" href={`/plan/today?c=${c}`}>Today&apos;s cost</Link>
          {analyst && <Link className="eg-btn eg-btn--ghost eg-btn--sm" href={`/settlement?c=${c}`}>Settlement explorer</Link>}
        </div>
      </div>
      <CompareBars d={d} />
      <div className="ep-sources">
        {d.sources.filter((s) => s.available).map((s) => <SourceCard key={s.id} s={s} avoided={avoided} analyst={analyst} />)}
      </div>
      <section className="eg-card ep-panel">
        <div className="eg-overline" style={{ marginBottom: 8 }}>Not available here yet</div>
        {d.sources.filter((s) => !s.available).map((s) => <p key={s.id} className="ep-small"><b>{s.label}</b> — {s.reason}</p>)}
        {Object.entries(d.gaps).map(([k, v]) => <p key={k} className="ep-small"><span className="eg-chip eg-chip--warning">{k.replaceAll("_", " ")}</span> {v}</p>)}
      </section>
    </>
  );
}
