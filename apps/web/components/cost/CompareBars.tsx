import type { LandedOut } from "@/lib/cost";

// Every available source against the grid's avoided cost, slot by slot (INR per kWh at the meter).
export function CompareBars({ d }: { d: LandedOut }) {
  const avoided = Object.fromEntries(d.avoided.map((a) => [a.slot, Number(a.rate.value)]));
  const rows = d.sources.filter((s) => s.available && s.id !== "discom_grid");
  const max = Math.max(...rows.flatMap((s) => s.by_slot.map((b) => Number(b.total.value))), ...Object.values(avoided), 1);
  return (
    <section className="eg-glass ep-panel">
      <div className="eg-card__head">
        <div>
          <h2 className="eg-card__title">Against the grid, slot by slot</h2>
          <p className="eg-card__sub">Bars are landed cost at the meter; the line is what a grid kWh costs you in that slot.</p>
        </div>
      </div>
      <div className="ep-compare">
        {d.slots.map((sl) => (
          <div key={sl.name} className="ep-compare__slot">
            <div className="eg-overline">{sl.name} <span className="eg-muted">({sl.start}–{sl.end})</span></div>
            {rows.map((s) => {
              const b = s.by_slot.find((x) => x.slot === sl.name);
              if (!b) return null;
              const v = Number(b.total.value);
              const a = avoided[sl.name];
              return (
                <div key={s.id} className="ep-compare__row" title={`${s.label}: ₹${v.toFixed(2)}/kWh`}>
                  <span className="ep-small">{s.label}</span>
                  <span className="ep-compare__track">
                    <span className={`ep-compare__bar${a !== undefined && v < a ? " ep-compare__bar--save" : ""}`} style={{ width: `${(v / max) * 100}%` }} />
                    {a !== undefined && <span className="ep-compare__grid" style={{ left: `${(a / max) * 100}%` }} />}
                  </span>
                  <span className="num ep-small">₹{v.toFixed(2)}</span>
                </div>
              );
            })}
            {avoided[sl.name] !== undefined && <div className="ep-small eg-muted">Grid: ₹{avoided[sl.name].toFixed(2)}/kWh</div>}
          </div>
        ))}
      </div>
    </section>
  );
}
