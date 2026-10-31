import Link from "next/link";
import { IntakeReview } from "@/components/intake/IntakeReview";
import { ProvenanceChip } from "@/components/intake/FactChip";
import { ProfileChart } from "@/components/intake/ProfileChart";
import { apiOrNull } from "@/lib/api";
import { monthLabel, type ConnectionOut, type ProfileOut, type SiteIntake } from "@/lib/intake";

// Journey step 4: describe the site (pattern, weekly off, shutdowns, existing assets) and see the
// 15-minute load profile built from the bills, month by month with where each number came from.
export default async function SitePage({ searchParams }: { searchParams: Promise<{ c?: string }> }) {
  const { c } = await searchParams;
  if (!c) {
    return (
      <section className="eg-card ep-panel">
        <h1 className="eg-h1">Describe the site</h1>
        <p className="eg-muted">Start with your bill first; this step opens once a site exists.</p>
        <Link className="eg-btn eg-btn--primary" href="/plan/intake">Drop a bill</Link>
      </section>
    );
  }
  const [conn, prof, intake] = await Promise.all([
    apiOrNull<ConnectionOut>(`/connections/${c}`),
    apiOrNull<ProfileOut>(`/connections/${c}/profile`),
    apiOrNull<SiteIntake>(`/connections/${c}/intake`),
  ]);
  if (!conn) return <p className="ep-empty">This site was not found.</p>;
  const total = prof?.months.reduce((s, m) => s + Number(m.energy_kwh.value), 0) ?? 0;
  const peak = prof ? Math.max(...prof.months.map((m) => Number(m.max_kw.value))) : 0;
  const billed = prof?.months.filter((m) => !m.extrapolated) ?? [];
  const pool = billed.length ? billed : prof?.months ?? [];
  const busiest = pool.length ? pool.reduce((a, b) => (Number(b.energy_kwh.value) > Number(a.energy_kwh.value) ? b : a)) : undefined;
  return (
    <>
      <div>
        <div className="eg-overline">Step 4 of 6</div>
        <h1 className="eg-h1">{conn.site.name}</h1>
        <p className="eg-muted ep-lede">
          {conn.client.name} · {conn.discom_id.toUpperCase()} · {conn.tariff_category} · {Number(conn.voltage_kv)} kV · contract demand {Number(conn.contract_demand_kva).toLocaleString("en-IN")} kVA
        </p>
      </div>
      <div className="ep-row">
        <Link className="eg-btn eg-btn--primary eg-btn--sm" href={`/plan/today?c=${c}`}>See today&apos;s cost</Link>
        <Link className="eg-btn eg-btn--ghost eg-btn--sm" href={`/plan/optimise?c=${c}`}>Optimise</Link>
      </div>
      {prof && (
        <section className="eg-glass ep-panel">
          <div className="eg-card__head">
            <div>
              <h2 className="eg-card__title">Your 15-minute load profile</h2>
              <p className="eg-card__sub">
                {prof.provenance === "measured" ? "Measured from your meter file." : "Built from your bills and the operating pattern; it matches each billed month's energy and recorded demand exactly."}
                {" "}Version {prof.version}.
              </p>
            </div>
            <div className="ep-row">
              <span className="eg-chip">{prof.provenance}</span>
              <a className="ep-cite" href={`/api/connections/${c}/profile.csv`}>Download the 35,040 blocks (CSV)</a>
            </div>
          </div>
          <div className="ep-stats">
            <div className="eg-stat"><div className="eg-stat__label">Energy in the year</div><div className="eg-stat__value">{(total / 1e6).toFixed(2)}<span className="eg-stat__unit"> GWh</span></div></div>
            <div className="eg-stat"><div className="eg-stat__label">Highest 15-minute demand</div><div className="eg-stat__value">{peak.toLocaleString("en-IN", { maximumFractionDigits: 0 })}<span className="eg-stat__unit"> kW</span></div></div>
            <div className="eg-stat"><div className="eg-stat__label">Months from bills</div><div className="eg-stat__value">{prof.months.filter((m) => !m.extrapolated).length}<span className="eg-stat__unit"> of 12</span></div></div>
          </div>
          <div className="eg-overline" style={{ margin: "var(--space-4) 0 var(--space-2)" }}>
            A week in {busiest ? monthLabel(busiest.month) : ""}
          </div>
          <ProfileChart kw={prof.week_kw.map(Number)} maxKw={busiest ? Number(busiest.max_kw.value) : undefined} />
          <table className="ep-table" style={{ marginTop: "var(--space-4)" }}>
            <thead><tr><th>Month</th><th className="num">Energy (kWh)</th><th className="num">Max demand (kW)</th><th>From</th></tr></thead>
            <tbody>
              {prof.months.map((m) => (
                <tr key={m.month}>
                  <td>{monthLabel(m.month)}</td>
                  <td className="num">{Number(m.energy_kwh.value).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</td>
                  <td className="num">
                    {Number(m.max_kw.value).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                    {m.peak_shortfall_kw && <span className="eg-chip eg-chip--warning" title="the pattern could not reach the recorded demand">short by {m.peak_shortfall_kw} kW</span>}
                  </td>
                  <td className="ep-row">
                    {m.energy_kwh.source_refs.map((r, i) => (
                      <ProvenanceChip key={i} provenance={r.kind === "client_stated" ? "client_stated" : r.kind === "bill" ? "bill" : r.kind === "measured" ? "measured" : "assumption"} refx={r} />
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      {intake ? (
        <IntakeReview initial={intake} connectionId={c} submitLabel="Rebuild the profile" />
      ) : (
        <p className="eg-muted">This profile was uploaded from a meter file; the site description is kept with the bills.</p>
      )}
    </>
  );
}
