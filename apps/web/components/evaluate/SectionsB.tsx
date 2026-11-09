"use client";

import Link from "next/link";
import { RefChips } from "@/components/cost/RefChips";
import { AssetsEditor } from "@/components/intake/AssetsEditor";
import { OPEN_ACCESS_CHOICES, OWNERSHIP_LABEL, TECH_GROUPS, inr, num, type DiscomOut, type Draft, type TodayOut } from "@/lib/evaluate";
import type { BillOut } from "@/lib/intake";
import type { SourceOption } from "@/lib/runs";
import { Advanced, Field, Note, Toggle } from "./ui";

type Set = (fn: (d: Draft) => Draft) => void;

// 4. Today's bill and open access
export function TodaySection({ d, set, today, bills, discom }: { d: Draft; set: Set; today: TodayOut | null; bills: BillOut[]; discom: DiscomOut | undefined }) {
  const t = d.today;
  const upd = (patch: Partial<Draft["today"]>) => set((cur) => ({ ...cur, today: { ...cur.today, ...patch } }));
  const accepted = bills.filter((b) => b.accepted);
  const billed = accepted.reduce((a, b) => a + Number(b.fields.find((f) => f.path === "money.net_payable")?.value ?? 0), 0);
  return (
    <>
      {d.connectionId ? (
        today ? (
          <div className="ep-stats">
            <div className="eg-stat"><span className="eg-stat__label">Grid cost today, a year</span><span className="eg-stat__value">{inr(today.annual?.value)}</span><span className="eg-stat__foot">at the approved tariff {today.annual && <RefChips refs={today.annual.source_refs} max={2} kinds={1} />}</span></div>
            <div className="eg-stat"><span className="eg-stat__label">Energy charges</span><span className="eg-stat__value">{inr(today.energy?.value)}</span><span className="eg-stat__foot">{num(today.kwh?.value)} kWh {today.kwh && <RefChips refs={today.kwh.source_refs} max={1} />}</span></div>
            <div className="eg-stat"><span className="eg-stat__label">Demand charges</span><span className="eg-stat__value">{inr(today.demand?.value)}</span><span className="eg-stat__foot">on billed demand</span></div>
            <div className="eg-stat"><span className="eg-stat__label">Average</span><span className="eg-stat__value">₹{today.average_inr_per_kwh ? Number(today.average_inr_per_kwh.value).toFixed(2) : "—"}</span><span className="eg-stat__foot">per kWh, all in</span></div>
          </div>
        ) : (
          <Note>Save the inputs above and today&apos;s cost appears here.</Note>
        )
      ) : (
        <Note>Once you save (button at the top right), ergPLAN rebuilds your bill from the tariff order and shows what a year costs today: energy, demand, time-of-day, each line linked to the order&apos;s page.</Note>
      )}
      {today?.gaps.length ? <p className="eg-muted ep-small">Not yet sourced for this DISCOM: {today.gaps.join("; ")}.</p> : null}
      {d.connectionId && accepted.length > 0 && (
        <p className="ep-small">
          {accepted.length} accepted bill{accepted.length > 1 ? "s" : ""}{billed > 0 ? `, ₹${num(billed)} billed` : ""}. <Link href={`/plan/today?c=${d.connectionId}`}>See each bill rebuilt line by line →</Link>
        </p>
      )}
      <div className="ep-grid2">
        <Field label="Open access you already take" help="Captive, group captive, third-party PPA or exchange power you already consume through open access. ergPLAN settles new sources under the same arrangement unless you choose otherwise, and the bill's set-off units confirm it." wide>
          <select value={t.open_access} onChange={(e) => upd({ open_access: e.target.value })}>
            <option value="">Not stated</option>
            {OPEN_ACCESS_CHOICES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
      </div>
      {discom && !discom.sourced.settlement && (
        <Note kind="warn">No approved banking and settlement rules for {discom.state_name} yet: open-access energy is set off block by block and nothing is banked until the state&apos;s regulation is read and approved. The plan says so wherever it matters.</Note>
      )}
      <h3 className="eg-overline" style={{ marginTop: 8 }}>Existing assets at the site</h3>
      <p className="eg-muted ep-small">Rooftop solar, DG sets, a battery or captive thermal you already have. They are kept in the plan; new sources are sized around them.</p>
      <AssetsEditor assets={t.assets} onChange={(assets) => upd({ assets })} />
    </>
  );
}

// 5. What to evaluate — technology toggles with their key inputs and an Advanced fold each.
export function TechSection({ d, set, options, discom }: { d: Draft; set: Set; options: SourceOption[]; discom: DiscomOut | undefined }) {
  const upd = (kind: string, patch: Partial<Draft["tech"][string]>) => set((cur) => ({ ...cur, tech: { ...cur.tech, [kind]: { ...cur.tech[kind], ...patch } } }));
  const groups = TECH_GROUPS.map((g) => ({ ...g, options: options.filter((o) => o.group === g.id) })).filter((g) => g.options.length);
  const n = options.filter((o) => d.tech[o.kind]?.on).length;
  return (
    <>
      <p className="eg-muted">
        Tick everything you would consider. The optimizer sizes each at least cost over a year of hourly blocks under {discom ? `${discom.state_name}'s` : "your state's"} open-access charges, losses and banking rules, and may leave a source at zero if it does not pay. {n} selected.
      </p>
      {groups.map((g) => (
        <fieldset key={g.id} className="ep-techgroup">
          <legend><b>{g.title}</b> <span className="eg-muted">{g.blurb}</span></legend>
          {g.options.map((o) => {
            const t = d.tech[o.kind] ?? { on: false, ownership: "", price: "", max_mw: "", min_mw: "", commissioned: "" };
            const exch = o.price_kind === "iex";
            return (
              <div key={o.kind} className={`ep-tech${t.on ? " ep-tech--on" : ""}${o.available ? "" : " ep-tech--off"}`}>
                <div className="ep-tech__head">
                  <Toggle on={t.on} label={o.label} onChange={(v) => o.available && upd(o.kind, { on: v })} />
                  <div className="ep-tech__name">
                    <b>{o.label}</b>
                    {!o.available && <span className="eg-chip eg-chip--warning" title={o.reason ?? undefined}>{o.reason ?? "not available"}</span>}
                    {o.connection === "ists" && <span className="eg-chip">inter-state</span>}
                  </div>
                </div>
                {t.on && (
                  <div className="ep-tech__body">
                    <div className="ep-grid3">
                      {o.ownerships.length > 0 && (
                        <Field label="Arrangement" help="Captive: you hold at least 26% of the plant's equity and take at least 51% of its energy, so the cross-subsidy surcharge and additional surcharge are waived. Group captive: the same, shared among several consumers. Third party: a PPA; the surcharges apply.">
                          <select value={t.ownership} onChange={(e) => upd(o.kind, { ownership: e.target.value })}>
                            {o.ownerships.map((w) => <option key={w} value={w}>{OWNERSHIP_LABEL[w] ?? w}</option>)}
                          </select>
                        </Field>
                      )}
                      {o.price_kind === "ppa" && (
                        <Field label="Tariff at the plant" unit="₹/kWh" help={`The price you pay the generator at its bus bar, before wheeling, losses and surcharges. Blank uses the 2026 market figure${o.default_price_inr_per_kwh ? ` (₹${o.default_price_inr_per_kwh}${o.price_note ? `: ${o.price_note}` : ""})` : ""}, marked as assumed.`}>
                          <input inputMode="decimal" value={t.price} onChange={(e) => upd(o.kind, { price: e.target.value })} placeholder={o.default_price_inr_per_kwh ?? ""} />
                        </Field>
                      )}
                      <Field label={exch ? "Most to buy" : "Largest size"} unit="MW" help={exch ? "The most power to schedule from the exchange in any block. Blank: up to your contract demand." : "A cap on the plant's size (land, approvals, appetite). Blank: the optimizer chooses, up to your contract demand (rooftop: your roof)."}>
                        <input inputMode="decimal" value={t.max_mw} onChange={(e) => upd(o.kind, { max_mw: e.target.value })} placeholder="no limit" />
                      </Field>
                    </div>
                    <Advanced>
                      <div className="ep-grid3">
                        <Field label="Smallest size" unit="MW" help="Force at least this much (an existing commitment, a minimum the developer will build).">
                          <input inputMode="decimal" value={t.min_mw} onChange={(e) => upd(o.kind, { min_mw: e.target.value })} placeholder="0" />
                        </Field>
                        {!exch && o.connection !== "behind_meter" && (
                          <Field label="Commissioning date" help="Inter-state transmission charges are waived for plants commissioned before the waiver's cut-off; some state orders tie banking terms to the commissioning year.">
                            <input type="date" value={t.commissioned} onChange={(e) => upd(o.kind, { commissioned: e.target.value })} />
                          </Field>
                        )}
                      </div>
                    </Advanced>
                  </div>
                )}
              </div>
            );
          })}
        </fieldset>
      ))}
    </>
  );
}

// 6. Analysis settings — the horizon, escalations and resolution.
export function SettingsSection({ d, set }: { d: Draft; set: Set }) {
  const s = d.settings;
  const upd = (patch: Partial<Draft["settings"]>) => set((cur) => ({ ...cur, settings: { ...cur.settings, ...patch } }));
  return (
    <>
      <div className="ep-grid3">
        <Field label="Analysis period" unit="years" help="The plan's lifetime for the lifecycle view: year-by-year cash flows, NPV and payback. 25 years is a solar plant's life; a battery is replaced within it.">
          <input inputMode="numeric" value={s.analysis_years} onChange={(e) => upd({ analysis_years: e.target.value })} />
        </Field>
        <Field label="Discount rate" unit="%" help="Your pre-tax cost of capital, used to bring each year's saving to today's money.">
          <input inputMode="decimal" value={s.discount_pct} onChange={(e) => upd({ discount_pct: e.target.value })} />
        </Field>
        <Field label="Tariff escalation" unit="% a year" help="How fast the DISCOM's tariff grows. The last decade averaged about 3% a year; set 0 to see the plan with today's tariff held flat.">
          <input inputMode="decimal" value={s.tariff_escalation_pct} onChange={(e) => upd({ tariff_escalation_pct: e.target.value })} />
        </Field>
        <Field label="PPA escalation" unit="% a year" help="How fast open-access and exchange prices grow. A PPA is usually fixed (0%); some step up 1–2%.">
          <input inputMode="decimal" value={s.ppa_escalation_pct} onChange={(e) => upd({ ppa_escalation_pct: e.target.value })} />
        </Field>
        <Field label="O&M escalation" unit="% a year" help="Growth of the running cost of owned plant (inflation).">
          <input inputMode="decimal" value={s.om_escalation_pct} onChange={(e) => upd({ om_escalation_pct: e.target.value })} />
        </Field>
        <Field label="Rules as of" help="The tariff order and open-access regulations in force on this date are applied to the whole year.">
          <input type="date" value={s.as_of} onChange={(e) => upd({ as_of: e.target.value })} />
        </Field>
      </div>
      <div className="ep-row" style={{ alignItems: "center", gap: 16 }}>
        <div className="eg-seg eg-seg--sm" role="group" aria-label="Resolution">
          {([60, 15] as const).map((m) => (
            <button key={m} aria-pressed={s.resolution_min === m} onClick={() => upd({ resolution_min: m })}>{m === 60 ? "Hourly year (8,760 blocks)" : "15-minute year (35,040 blocks)"}</button>
          ))}
        </div>
        <span className="eg-muted ep-small">{s.resolution_min === 60 ? "About a minute to size." : "Several minutes; the precise setting for the final plan."}</span>
      </div>
      <label className="ep-check">
        <input type="checkbox" checked={s.standard_plans} onChange={(e) => upd({ standard_plans: e.target.checked })} />
        Also size jouleWise&apos;s three reference plans (captive solar; hybrid with a battery; rooftop, captive solar and a battery) to compare with your mix
      </label>
    </>
  );
}
