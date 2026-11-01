"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { clientFetch, monthLabel, refHref, type SiteIntake } from "@/lib/intake";
import { indian, type PlanInputs, type PlanValue } from "@/lib/reading";

const UNIT: Record<string, string> = { "INR/kVAh": "₹/kVAh", "INR/kWh": "₹/kWh", INR: "₹", percent: "%", ratio: "", kVA: "kVA", kVAh: "kVAh", kWh: "kWh" };

function Figure({ v, big }: { v: PlanValue; big?: boolean }) {
  const unit = UNIT[v.value.unit] ?? v.value.unit;
  const ref = v.value.source_refs[0];
  const href = refHref(ref);
  const money = v.value.unit === "INR";
  const text = `${money ? "₹" : ""}${indian(v.value.value)}${!money && unit ? ` ${unit}` : ""}`;
  return (
    <span className={`ep-figure${big ? " ep-figure--big" : ""}${v.verification && v.verification !== "verified" && v.verification !== "confirmed" ? " is-check" : ""}`}>
      {href ? <a href={href} target="_blank" rel="noreferrer" title={`${v.label}${ref?.page ? `, page ${ref.page}` : ""}`}>{text}</a> : text}
    </span>
  );
}

// What RE planning takes from one bill: the slot table (consumed, open access set off, billed by the
// DISCOM, the slot's rate), the demand, and shares derived from them. Every figure opens its page.
export function PlanInputsView({ inputs }: { inputs: PlanInputs }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const month = inputs.bill_month;
  const maxShare = Math.max(1, ...inputs.slots.map((s) => Number(s.share_of_consumption?.value.value ?? 0)));

  async function next() {
    setBusy(true);
    setError("");
    try {
      const intake = await clientFetch<SiteIntake>("/intake/from-bills", { method: "POST", body: JSON.stringify({ bill_ids: [inputs.bill_id] }) });
      sessionStorage.setItem("ergplan-intake", JSON.stringify(intake));
      router.push("/plan/intake?review=1");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ep-handoff">
      <div>
        <div className="eg-overline">From the bill to the plan</div>
        <h1 className="eg-h1">What planning takes from {month ? monthLabel(month.length === 7 ? `${month}-01` : month) : "this bill"}</h1>
        <p className="eg-muted ep-lede">
          {inputs.discom ? inputs.discom.toUpperCase() : "DISCOM not recognised"}{inputs.tariff_category ? ` · ${inputs.tariff_category}` : ""} · figures in {inputs.energy_unit}.
          Each figure links to the page it was read from.
        </p>
      </div>

      <section className="ep-cards">
        {inputs.facts.map((f) => (
          <article key={f.key} className="eg-card ep-stat">
            <div className="ep-stat__label">{f.label}</div>
            <Figure v={f} big />
          </article>
        ))}
        {inputs.derived.map((f) => (
          <article key={f.key} className="eg-card ep-stat ep-stat--derived">
            <div className="ep-stat__label">{f.label}</div>
            <Figure v={f} big />
            <small className="eg-muted">worked out from {f.value.source_refs.length} figures on the bill</small>
          </article>
        ))}
      </section>

      {inputs.slots.length > 0 && (
        <section className="eg-card ep-panel">
          <h2 className="eg-card__title">The day, slot by slot</h2>
          <p className="eg-card__sub">Your load profile is built so each slot&apos;s energy matches these figures exactly.</p>
          <table className="ep-table">
            <thead>
              <tr><th>Slot</th><th>Hours</th><th>Share of the month</th><th className="num">Consumed</th><th className="num">Open access</th><th className="num">Billed</th><th className="num">Rate</th></tr>
            </thead>
            <tbody>
              {inputs.slots.map((s) => {
                const share = Number(s.share_of_consumption?.value.value ?? 0);
                return (
                  <tr key={s.slot}>
                    <td>{s.slot}</td>
                    <td className="nowrap">{s.start && s.end ? `${s.start}–${s.end}` : <span className="eg-muted">not printed</span>}</td>
                    <td>
                      <span className="ep-share"><span style={{ width: `${(share / maxShare) * 100}%` }}></span></span>
                      <small>{s.share_of_consumption ? `${s.share_of_consumption.value.value}%` : "—"}</small>
                    </td>
                    <td className="num">{s.consumption ? <Figure v={s.consumption} /> : "—"}</td>
                    <td className="num">{s.open_access ? <Figure v={s.open_access} /> : "—"}</td>
                    <td className="num">{s.billed ? <Figure v={s.billed} /> : "—"}</td>
                    <td className="num">{s.rate ? <Figure v={s.rate} /> : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      {inputs.notes.map((n) => <p key={n} className="eg-muted ep-note">{n}</p>)}
      {error && <p className="ep-error">{error}</p>}
      <div className="ep-row">
        <Link className="eg-btn eg-btn--ghost" href={`/plan/intake/bill/${inputs.bill_id}`}>Back to the bill</Link>
        <button className="eg-btn eg-btn--primary" onClick={next} disabled={busy || !inputs.accepted}
          title={inputs.accepted ? undefined : "Confirm the values marked for checking first"}>
          {busy ? "Preparing…" : "Use this bill for the plan"}
        </button>
      </div>
    </div>
  );
}
