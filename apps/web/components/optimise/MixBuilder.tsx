"use client";

import { useEffect, useMemo, useState } from "react";
import { clientFetch } from "@/lib/intake";
import type { CandidateSpec, SourceOption } from "@/lib/runs";

type Pick = { on: boolean; ownership: string; price: string; max: string };
const OWNERSHIP: Record<string, string> = { captive: "Captive", group_captive: "Group captive", third_party: "Third party" };
const START = new Set(["oa_solar_intra", "oa_wind_intra", "iex_dam"]);

// Journey step 5: the client picks the sources to weigh (open-access solar, wind and hybrid, intra-state or ISTS;
// rooftop solar and a battery at the site; purchases on the power exchange, segment by segment) and the plan finds
// the least-cost size of each over a year of 15-minute blocks, settled under the state's rules. Buy only on the exchange.
export function MixBuilder({ connectionId, asOf, defaultOwnership, onQueued }: {
  connectionId: string; asOf: string; defaultOwnership: string | null; onQueued: () => void;
}) {
  const [options, setOptions] = useState<SourceOption[]>([]);
  const [picks, setPicks] = useState<Record<string, Pick>>({});
  const [minutes, setMinutes] = useState<15 | 60>(15);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  useEffect(() => {
    clientFetch<SourceOption[]>(`/connections/${connectionId}/mix/options`)
      .then((o) => {
        setOptions(o);
        setPicks(Object.fromEntries(o.map((x) => [x.kind, {
          on: x.available && START.has(x.kind),
          ownership: x.ownerships.includes(defaultOwnership ?? "") ? (defaultOwnership as string) : x.ownerships[0] ?? "",
          price: "",
          max: "",
        }])));
      })
      .catch((e) => setError((e as Error).message));
  }, [connectionId, defaultOwnership]);

  const groups = useMemo(() => {
    const out: Record<string, SourceOption[]> = {};
    for (const o of options) (out[o.group] ??= []).push(o);
    return out;
  }, [options]);
  const chosen = options.filter((o) => picks[o.kind]?.on);

  function set(kind: string, patch: Partial<Pick>) {
    setPicks({ ...picks, [kind]: { ...picks[kind], ...patch } });
  }

  async function run() {
    setBusy(true);
    setError("");
    setDone("");
    const sources: CandidateSpec[] = chosen.map((o) => {
      const p = picks[o.kind];
      const c: CandidateSpec = { kind: o.kind };
      if (o.ownerships.length && p.ownership) c.ownership = p.ownership;
      if (p.price.trim() && o.price_kind === "ppa") c.price_inr_per_kwh = p.price.trim();
      if (p.max.trim()) c.max_mw = p.max.trim();
      return c;
    });
    try {
      await clientFetch(`/connections/${connectionId}/mix`, {
        method: "POST",
        body: JSON.stringify({ sources, resolution_min: minutes, as_of: asOf }),
      });
      setDone(minutes === 15
        ? "Sizing your mix over 35,040 fifteen-minute blocks; it appears below as “Your mix” in a minute or two."
        : "Sizing your mix hourly; it appears below as “Your mix” shortly.");
      onQueued();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="eg-card ep-panel ep-mix">
      <div className="eg-card__head">
        <div>
          <h2 className="eg-card__title">Build your own mix</h2>
          <p className="eg-card__sub">Tick every source you would consider. The plan finds the size of each that costs least over a year of 15-minute blocks, with the open-access charges, losses and banking rules of your state; the exchange is bought block by block at its clearing price, never sold to.</p>
        </div>
      </div>
      {Object.entries(groups).map(([g, opts]) => (
        <fieldset key={g} className="ep-mix__group">
          <legend className="eg-overline">{g}</legend>
          {opts.map((o) => {
            const p = picks[o.kind];
            if (!p) return null;
            return (
              <div key={o.kind} className={`ep-mix__row${p.on ? " ep-mix__row--on" : ""}`}>
                <label className="ep-mix__pick">
                  <input type="checkbox" checked={p.on} disabled={!o.available} onChange={(e) => set(o.kind, { on: e.target.checked })} />
                  <span>{o.label}</span>
                  {!o.available && <span className="eg-chip eg-chip--warning" title={o.reason ?? undefined}>{o.reason}</span>}
                </label>
                {p.on && (
                  <div className="ep-mix__opts">
                    {o.ownerships.length > 0 && (
                      <label className="eg-field"><span className="eg-field__label">Arrangement</span><span className="eg-input">
                        <select value={p.ownership} onChange={(e) => set(o.kind, { ownership: e.target.value })}>
                          {o.ownerships.map((w) => <option key={w} value={w}>{OWNERSHIP[w] ?? w}</option>)}
                        </select></span></label>
                    )}
                    {o.price_kind === "ppa" && (
                      <label className="eg-field"><span className="eg-field__label">Tariff ₹/kWh</span><span className="eg-input">
                        <input inputMode="decimal" placeholder={o.default_price_inr_per_kwh ?? ""} title={o.price_note ?? undefined} value={p.price} onChange={(e) => set(o.kind, { price: e.target.value })} />
                      </span></label>
                    )}
                    <label className="eg-field"><span className="eg-field__label">{o.price_kind === "iex" ? "Most to buy, MW" : "Largest size, MW"}</span><span className="eg-input">
                      <input inputMode="decimal" placeholder="no limit" value={p.max} onChange={(e) => set(o.kind, { max: e.target.value })} />
                    </span></label>
                  </div>
                )}
              </div>
            );
          })}
        </fieldset>
      ))}
      <div className="ep-row">
        <div className="eg-seg eg-seg--sm" role="group" aria-label="Resolution">
          {([15, 60] as const).map((m) => (
            <button key={m} className="ep-seglink" aria-current={minutes === m ? "true" : undefined} onClick={() => setMinutes(m)}>{m === 15 ? "15-minute year" : "Hourly preview"}</button>
          ))}
        </div>
        <button className="eg-btn eg-btn--primary" disabled={busy || chosen.length === 0} onClick={run}>{busy ? "Queuing…" : `Find the least-cost mix of ${chosen.length} source${chosen.length === 1 ? "" : "s"}`}</button>
        <span className="eg-muted ep-small">A blank tariff uses the 2026 market figure shown, marked as assumed.</span>
      </div>
      {done && <p className="ep-note">{done}</p>}
      {error && <p className="ep-error">{error}</p>}
    </section>
  );
}
