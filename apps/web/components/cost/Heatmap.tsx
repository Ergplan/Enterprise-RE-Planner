import { hhmm, inr, type AvoidedOut, uniqueRefs } from "@/lib/cost";
import { monthLabel } from "@/lib/intake";
import { RefChips } from "./RefChips";

// Avoided cost of one grid kWh, month × time of day (the 35,040 blocks are exactly this matrix).
export function Heatmap({ a }: { a: AvoidedOut }) {
  const value = (i: number) => (i >= 0 ? Number(a.cards[i].rate.value) : 0);
  const flat = a.matrix.flat().map(value).filter((v) => v > 0);
  const lo = Math.min(...flat);
  const hi = Math.max(...flat);
  const months = a.matrix.map((_, i) => {
    const d = new Date(a.year_start + "T00:00:00Z");
    d.setUTCMonth(d.getUTCMonth() + i);
    return d.toISOString().slice(0, 10);
  });
  const level = (v: number) => (v <= 0 || hi === lo ? 0 : Math.round(((v - lo) / (hi - lo)) * 100));
  const energy = a.annual[0];
  const demand = a.annual.find((x) => x.label === "Demand charges (year)");
  const slots = new Map<string, (typeof a.cards)[number]>();
  for (const c of a.cards) if (!slots.has(c.slot ?? "")) slots.set(c.slot ?? "", c);
  return (
    <section className="eg-glass ep-panel">
      <div className="eg-card__head">
        <div>
          <h2 className="eg-card__title">What a grid kWh costs you, every 15 minutes</h2>
          <p className="eg-card__sub">The avoided cost of one unit from the grid under the tariff in force on {a.tariff_as_of}, over your load profile (v{a.profile_version}, {a.profile_provenance}).</p>
        </div>
      </div>
      {flat.length === 0 ? (
        <p className="ep-empty">No approved tariff applies to this connection yet.</p>
      ) : (
        <>
          <div className="ep-stats">
            {energy && <div className="eg-stat"><div className="eg-stat__label">Energy at these rates, a year</div><div className="eg-stat__value">{inr(Number(energy.value) / 1e7, 2)}<span className="eg-stat__unit"> crore</span></div><RefChips refs={uniqueRefs([energy])} max={2} /></div>}
            {demand && <div className="eg-stat"><div className="eg-stat__label">Demand charges, a year</div><div className="eg-stat__value">{inr(Number(demand.value) / 1e7, 2)}<span className="eg-stat__unit"> crore</span></div><RefChips refs={uniqueRefs([demand])} max={2} /></div>}
            <div className="eg-stat"><div className="eg-stat__label">Range per kWh</div><div className="eg-stat__value">₹{lo.toFixed(2)}–{hi.toFixed(2)}</div></div>
          </div>
          <div className="ep-heat" role="img" aria-label="Avoided cost by month and time of day">
            <div className="ep-heat__row ep-heat__axis"><span></span>{Array.from({ length: 24 }, (_, h) => <span key={h} style={{ gridColumn: `span 4` }}>{h % 3 === 0 ? `${h}h` : ""}</span>)}</div>
            {a.matrix.map((row, m) => (
              <div key={m} className="ep-heat__row">
                <span className="eg-muted">{monthLabel(months[m]).replace(" 20", " ’")}</span>
                {row.map(value).map((v, b) => (
                  <span key={b} className="ep-heat__cell" style={{ ["--lvl" as string]: `${Number(v) > 0 ? 15 + Math.round(level(Number(v)) * 0.85) : 0}%` }}
                    title={`${monthLabel(months[m])} ${hhmm(b)}–${hhmm(b + 1)}: ₹${Number(v).toFixed(3)}/kWh`} />
                ))}
              </div>
            ))}
          </div>
          <table className="ep-table" style={{ marginTop: "var(--space-4)" }}>
            <thead><tr><th>ToD slot</th><th className="num">₹ per kWh</th><th>Built from</th><th>Sources</th></tr></thead>
            <tbody>
              {[...slots.values()].map((c) => (
                <tr key={c.slot ?? "all"}>
                  <td>{c.slot ?? "all hours"} <span className="eg-muted ep-small">({monthLabel(c.month)})</span></td>
                  <td className="num">{Number(c.rate.value).toFixed(3)}</td>
                  <td className="eg-muted ep-small">
                    {c.components.map((x) => `${x.label} ${Number(x.value).toFixed(3)}`).join(" + ")}
                    {c.kvah_factor ? ` × ${Number(c.kvah_factor.value).toFixed(4)} kVAh/kWh` : ""}
                  </td>
                  <td><RefChips refs={uniqueRefs([c.rate])} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {(Object.keys(a.gaps).length > 0) && (
        <div className="ep-gaps">
          {Object.entries(a.gaps).map(([k, v]) => <p key={k}><span className="eg-chip eg-chip--warning">not included: {k.replaceAll("_", " ")}</span> {v}</p>)}
        </div>
      )}
    </section>
  );
}
