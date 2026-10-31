import type { LandedSource } from "@/lib/cost";
import { uniqueRefs } from "@/lib/cost";
import { RefChips } from "./RefChips";

// One source's landed cost at the meter, per ToD slot: the waterfall lines with their citations.
export function SourceCard({ s, avoided, analyst }: { s: LandedSource; avoided: Record<string, number>; analyst: boolean }) {
  const first = s.by_slot[0];
  const same = s.by_slot.every((b) => b.total.value === first?.total.value);
  const shown = same ? s.by_slot.slice(0, 1) : s.by_slot;

  return (
    <article className="eg-card ep-source">
      <div className="eg-card__head">
        <div>
          <h3 className="eg-card__title">{s.label}</h3>
          {!s.available && <p className="eg-card__sub">{s.reason}</p>}
        </div>
        {first && (
          <div className="ep-source__total">
            <b>₹{Number(first.total.value).toFixed(2)}</b><span className="eg-muted">/kWh{same ? "" : ` · ${first.slot}`}</span>
          </div>
        )}
      </div>
      {!same && (
        <table className="ep-table">
          <tbody>
            {s.by_slot.map((b) => (
              <tr key={b.slot}>
                <td>{b.slot}</td>
                <td className="num">₹{Number(b.total.value).toFixed(3)}</td>
                <td className="ep-small">{s.id !== "discom_grid" && avoided[b.slot] !== undefined && <Versus v={Number(b.total.value)} a={avoided[b.slot]} />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {shown.map((b) => (
        <details key={b.slot} className="ep-details" open={same}>
          <summary>{same ? "How it adds up" : `How it adds up · ${b.slot}`}</summary>
          <table className="ep-table">
            <tbody>
              {b.lines.map((l, i) => (
                <tr key={i}>
                  <td>{l.label ?? (i === 0 ? "Price" : "")}</td>
                  <td className="num">{Number(l.value) >= 0 ? "" : "−"}₹{Math.abs(Number(l.value)).toFixed(3)}</td>
                  <td><RefChips refs={uniqueRefs([l])} max={2} /></td>
                </tr>
              ))}
              <tr className="ep-total">
                <td>At the meter</td>
                <td className="num">₹{Number(b.total.value).toFixed(3)}</td>
                <td className="ep-small">{s.id !== "discom_grid" && avoided[b.slot] !== undefined && <Versus v={Number(b.total.value)} a={avoided[b.slot]} />}</td>
              </tr>
            </tbody>
          </table>
        </details>
      ))}
      {same && s.by_slot.length > 1 && <p className="eg-muted ep-small">The same in every ToD slot ({s.by_slot.map((b) => b.slot).join(", ")}).</p>}
      {s.gaps.length > 0 && <p className="ep-small"><span className="eg-chip eg-chip--warning">not yet sourced</span> {s.gaps.map((g) => g.replaceAll("_", " ")).join(", ")}</p>}
      {s.notes.map((n) => <p key={n} className="eg-muted ep-small">{n}</p>)}
      {analyst && s.rules_used.length > 0 && <p className="eg-muted ep-small">Rule rows: {s.rules_used.map((r) => r.slice(0, 8)).join(", ")}</p>}
    </article>
  );
}

function Versus({ v, a }: { v: number; a: number }) {
  return (
    <span className={`eg-chip ${v < a ? "eg-chip--accent" : "eg-chip--negative"}`}>
      {v < a ? "saves" : "costs"} ₹{Math.abs(a - v).toFixed(2)} vs grid
    </span>
  );
}
