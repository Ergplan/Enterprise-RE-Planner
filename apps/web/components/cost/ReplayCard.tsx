import { inr, type ReplayOut, uniqueRefs } from "@/lib/cost";
import { monthLabel } from "@/lib/intake";
import { RefChips } from "./RefChips";

const STATUS: Record<string, { label: string; tone: string }> = {
  match: { label: "matches", tone: "eg-chip--accent" },
  explained: { label: "explained", tone: "eg-chip--warning" },
  unexplained: { label: "differs", tone: "eg-chip--negative" },
  not_billed: { label: "not billed", tone: "" },
};

// One bill rebuilt from the approved tariff beside what the DISCOM charged.
export function ReplayCard({ r }: { r: ReplayOut }) {
  const st = STATUS[r.status] ?? STATUS.unexplained;
  // Totals over the lines the approved rules compute, so the two sides cover the same charges.
  const rebuilt = r.lines.filter((l) => l.computed);
  const billedSum = rebuilt.reduce((s, l) => s + Number(l.billed ?? 0), 0);
  const computedSum = rebuilt.reduce((s, l) => s + Number(l.computed?.value ?? 0), 0);
  const elsewhere = r.lines.filter((l) => !l.computed).reduce((s, l) => s + Number(l.billed ?? 0), 0);
  return (
    <section className="eg-glass ep-panel">
      <div className="eg-card__head">
        <div>
          <h2 className="eg-card__title">{r.bill_month ? monthLabel(r.bill_month) : r.evaluated_on} bill, rebuilt</h2>
          <p className="eg-card__sub">
            {r.schedule ? <>Tariff: {r.schedule}{r.tod ? ` · ToD: ${r.tod}` : ""}. </> : "No approved tariff covers this bill's dates. "}
            Evaluated for {r.evaluated_on}.
          </p>
        </div>
        <div className="ep-row">
          <span className={`eg-chip ${st.tone}`}>{st.label}</span>
          <a className="ep-cite" href={`/api${r.file_url}`} target="_blank" rel="noreferrer"><span data-icon="file" data-size="14"></span>Open the bill</a>
        </div>
      </div>
      <table className="ep-table ep-replay">
        <thead>
          <tr><th>Line</th><th className="num">On the bill</th><th className="num">Rebuilt</th><th className="num">Difference</th><th>Status</th><th>Sources</th></tr>
        </thead>
        <tbody>
          {r.lines.map((l) => {
            const s = STATUS[l.status] ?? STATUS.unexplained;
            return (
              <tr key={l.group} className={l.status === "unexplained" ? "ep-diff" : undefined}>
                <td>
                  {l.label}
                  {l.billed_items.length > 1 && <div className="eg-muted ep-small">{l.billed_items.join(" · ")}</div>}
                </td>
                <td className="num">{inr(l.billed, 2)}</td>
                <td className="num">{l.computed ? inr(l.computed.value, 2) : <span className="eg-muted">not yet sourced</span>}</td>
                <td className="num">{Math.abs(Number(l.difference)) < 1 ? "—" : inr(l.difference, 2)}</td>
                <td><span className={`eg-chip ${s.tone}`} title={l.explanation}>{s.label}</span></td>
                <td>{l.computed ? <RefChips refs={uniqueRefs([l.computed])} /> : <span className="eg-muted ep-small" title={l.explanation}>{l.status === "explained" && l.gap ? "rule gap" : ""}</span>}</td>
              </tr>
            );
          })}
          <tr className="ep-total">
            <td>Lines rebuilt from the tariff order</td>
            <td className="num">{inr(billedSum, 2)}</td>
            <td className="num">{inr(computedSum, 2)}</td>
            <td className="num">{Math.abs(computedSum - billedSum) < 1 ? "—" : inr(computedSum - billedSum, 2)}</td>
            <td colSpan={2} className="eg-muted ep-small">Other lines on the bill (not yet sourced): {inr(elsewhere, 2)}</td>
          </tr>
        </tbody>
      </table>
      {r.tariff_lines.length > 0 && (
        <details className="ep-details">
          <summary>How the rebuilt lines are computed</summary>
          <table className="ep-table">
            <tbody>
              {r.tariff_lines.map((t, i) => (
                <tr key={i}>
                  <td>{t.label}</td>
                  <td className="num eg-muted">
                    {t.quantity ? `${Number(t.quantity.value).toLocaleString("en-IN")} ${t.quantity.unit}` : ""}
                    {t.quantity && t.rate ? " × " : ""}
                    {t.rate ? `${t.rate.value} ${t.rate.unit}` : ""}
                  </td>
                  <td className="num">{inr(t.amount.value, 2)}</td>
                  <td><RefChips refs={uniqueRefs([t.rate ?? t.amount])} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
      {(Object.keys(r.gaps).length > 0 || r.notes.length > 0) && (
        <div className="ep-gaps">
          {Object.entries(r.gaps).map(([k, v]) => <p key={k}><span className="eg-chip eg-chip--warning">{k.replaceAll("_", " ")}</span> {v}</p>)}
          {r.notes.map((n) => <p key={n} className="eg-muted">{n}</p>)}
        </div>
      )}
    </section>
  );
}
