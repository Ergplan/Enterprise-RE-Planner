import Link from "next/link";
import { apiOrNull } from "@/lib/api";
import { inr, type EvaluationOut } from "@/lib/evaluate";

// Home: the evaluations this account can see, and the way in.
export default async function Home() {
  const rows = (await apiOrNull<EvaluationOut[]>("/connections")) ?? [];
  return (
    <>
      <div className="ep-hero">
        <div>
          <div className="eg-overline">ergPLAN</div>
          <h1 className="eg-h1">Plan your factory&apos;s move to green power</h1>
          <p className="eg-muted ep-lede">
            Describe the factory, drop its bills, tick the sources you would consider: rooftop solar, a battery, open-access solar, wind or hybrid,
            the power exchange. ergPLAN sizes them at least cost over a year, settles the energy under your state&apos;s banking rules, and shows
            the saving over 25 years — every figure linked to the tariff order or regulation it comes from.
          </p>
          <div className="ep-row">
            <Link className="eg-btn eg-btn--primary eg-btn--lg" href="/evaluate">
              New evaluation <span data-icon="arrow-right" data-size="16"></span>
            </Link>
            <Link className="eg-btn eg-btn--ghost" href="/documents">The regulation library</Link>
          </div>
        </div>
        <ol className="ep-hero__steps">
          <li><b>Your factory</b><span>name, state, how it runs</span></li>
          <li><b>DISCOM and connection</b><span>read from your bills, or picked</span></li>
          <li><b>Consumption</b><span>twelve months of units</span></li>
          <li><b>Today&apos;s bill</b><span>rebuilt from the tariff order</span></li>
          <li><b>What to evaluate</b><span>solar, wind, battery, exchange</span></li>
          <li><b>Results</b><span>sizes, savings, 25-year cash flows</span></li>
        </ol>
      </div>

      <section className="eg-card ep-panel">
        <div className="eg-card__head">
          <div>
            <h2 className="eg-card__title">Your evaluations</h2>
            <p className="eg-card__sub">{rows.length ? `${rows.length} site${rows.length > 1 ? "s" : ""}` : "None yet — start one above."}</p>
          </div>
        </div>
        {rows.length > 0 && (
          <table className="ep-table ep-evals">
            <thead><tr><th>Site</th><th>DISCOM</th><th>Contract demand</th><th>Inputs</th><th>Latest result</th><th></th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.connection_id}>
                  <td><b>{r.client}</b><div className="eg-muted ep-small">{r.site}{r.state ? ` · ${r.state}` : ""}</div></td>
                  <td>{r.discom.toUpperCase()}{r.category ? <div className="eg-muted ep-small">{r.category}</div> : null}</td>
                  <td className="num">{r.contract_demand_kva ? `${Number(r.contract_demand_kva).toLocaleString("en-IN")} kVA` : "—"}</td>
                  <td>{r.bills ? `${r.bills} bill${r.bills > 1 ? "s" : ""}` : "typed"}{r.profile_provenance ? <div className="eg-muted ep-small">{r.profile_provenance} profile</div> : null}</td>
                  <td>
                    {r.latest_run ? (
                      r.latest_run.status === "done" ? (
                        <><b>{inr(r.latest_run.saving?.value)}</b> a year<div className="eg-muted ep-small">{r.latest_run.scenario}</div></>
                      ) : (
                        <span className="eg-chip">{r.latest_run.status.replace("_", " ")}</span>
                      )
                    ) : <span className="eg-muted">not sized yet</span>}
                  </td>
                  <td className="ep-actions">
                    <Link className="eg-btn eg-btn--sm eg-btn--ghost" href={`/evaluate?c=${r.connection_id}`}>Inputs</Link>
                    <Link className="eg-btn eg-btn--sm eg-btn--primary" href={r.latest_run ? `/results?c=${r.connection_id}` : `/evaluate?c=${r.connection_id}`}>{r.latest_run ? "Results" : "Size it"}</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
