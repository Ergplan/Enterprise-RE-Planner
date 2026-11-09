"use client";

import { useCallback, useRef, useState } from "react";
import { BillReview } from "@/components/intake/BillReview";
import { ReadingCard } from "@/components/intake/ReadingCard";
import { DAYS, clientFetch, type BillOut, type ShapeOut } from "@/lib/intake";
import type { BillReadOut, PlanInputs } from "@/lib/reading";
import type { DiscomOut, Draft } from "@/lib/evaluate";
import { Advanced, Field, Note } from "./ui";

type Set = (fn: (d: Draft) => Draft) => void;

// 1. Your factory
export function FactorySection({ d, set, shapes, discoms }: { d: Draft; set: Set; shapes: ShapeOut[]; discoms: DiscomOut[] }) {
  const states = [...new Map(discoms.map((x) => [x.state, x.state_name])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
  const ready = new Set(discoms.filter((x) => x.ready).map((x) => x.state));
  const f = d.factory;
  const upd = (patch: Partial<Draft["factory"]>) => set((cur) => ({ ...cur, factory: { ...cur.factory, ...patch } }));
  return (
    <div className="ep-grid2">
      <Field label="Company" required help="The name on the electricity bill, or the group company. It appears on the plan.">
        <input value={f.client_name} onChange={(e) => upd({ client_name: e.target.value })} placeholder="e.g. Acme Forgings Ltd" />
      </Field>
      <Field label="Site or town" required help="Which factory this plan is for; a company with several sites gets one plan each.">
        <input value={f.site_name} onChange={(e) => upd({ site_name: e.target.value })} placeholder="e.g. Greater Noida unit 2" />
      </Field>
      <Field label="State" required help="The state decides the regulator, the open-access and banking rules and the solar and wind resource used for sizing.">
        <select value={f.state} onChange={(e) => { upd({ state: e.target.value }); set((cur) => ({ ...cur, connection: { ...cur.connection, discom: "", category: "" } })); }}>
          <option value="">Choose…</option>
          {states.map(([code, name]) => <option key={code} value={code}>{name}{ready.has(code) ? "" : " (tariff not yet sourced)"}</option>)}
        </select>
      </Field>
      <Field label="How the plant runs" required help="The daily pattern shapes the load profile built from your monthly units: a two-shift plant peaks in the day, a continuous process is flat.">
        <select value={f.industry_shape} onChange={(e) => {
          const sh = shapes.find((x) => x.id === e.target.value);
          upd({ industry_shape: e.target.value, weekly_off: sh ? [0, 1, 2, 3, 4, 5, 6].filter((x) => !sh.working_days.includes(x)) : f.weekly_off });
        }}>
          {shapes.map((s) => <option key={s.id} value={s.id} title={s.note ?? undefined}>{s.name}</option>)}
        </select>
      </Field>
      <div className="ep-fld ep-fld--wide">
        <div className="ep-fld__head"><span className="eg-field__label">Weekly off</span></div>
        <div className="ep-days">
          {DAYS.map((name, i) => (
            <label key={name} className={`eg-chip ep-day${f.weekly_off.includes(i) ? " ep-day--off" : ""}`}>
              <input type="checkbox" hidden checked={f.weekly_off.includes(i)} onChange={(e) => upd({ weekly_off: e.target.checked ? [...f.weekly_off, i].sort() : f.weekly_off.filter((x) => x !== i) })} />
              {name}
            </label>
          ))}
          <span className="eg-muted ep-small">ticked = the plant is off</span>
        </div>
      </div>
      <Advanced label="Land and roof (limits rooftop and captive solar)">
        <div className="ep-grid2">
          <Field label="Usable roof" unit="m²" help="Rooftop solar needs about 10 m² per kWp. Leave blank and rooftop solar is limited by your contract demand instead.">
            <input inputMode="decimal" value={f.roof_sqm} onChange={(e) => upd({ roof_sqm: e.target.value })} placeholder="e.g. 8000" />
          </Field>
          <Field label="Free land" unit="acres" help="Ground-mounted solar at the site needs about 4 acres per MW. Not used for open-access plants, which stand elsewhere.">
            <input inputMode="decimal" value={f.land_acres} onChange={(e) => upd({ land_acres: e.target.value })} placeholder="e.g. 12" />
          </Field>
        </div>
      </Advanced>
    </div>
  );
}

// 2. DISCOM and connection — from bills (billx reads them) or picked from lists.
export function ConnectionSection({ d, set, discoms, bills, onBills, planInputs }: {
  d: Draft; set: Set; discoms: DiscomOut[]; bills: BillOut[]; onBills: (b: BillOut[]) => void; planInputs: PlanInputs | null;
}) {
  const [reads, setReads] = useState<BillReadOut[]>([]);
  const [uploading, setUploading] = useState(0);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const c = d.connection;
  const upd = (patch: Partial<Draft["connection"]>) => set((cur) => ({ ...cur, connection: { ...cur.connection, ...patch } }));
  const inState = discoms.filter((x) => !d.factory.state || x.state === d.factory.state);
  const discom = discoms.find((x) => x.id === c.discom);
  const cats = discom?.categories ?? [];
  const catCodes = [...new Set(cats.map((x) => x.code))];
  const cat = cats.find((x) => x.code === c.category);

  async function upload(files: FileList | File[]) {
    setError("");
    const list = Array.from(files).filter((f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
    if (list.length === 0) { setError("Bills are read from PDF files."); return; }
    setUploading((n) => n + list.length);
    await Promise.all(list.map(async (f) => {
      const fd = new FormData();
      fd.append("file", f);
      if (d.connectionId) fd.append("connection_id", d.connectionId);
      try {
        const read = await clientFetch<BillReadOut>("/bill-reads", { method: "POST", body: fd });
        if (read.status === "done") onBills(read.bills);
        else setReads((cur) => [...cur.filter((x) => x.id !== read.id), read]);
      } catch (e) {
        setError(`${f.name}: ${(e as Error).message}`);
      } finally {
        setUploading((n) => n - 1);
      }
    }));
  }
  const readDone = useCallback((r: BillReadOut) => {
    setReads((cur) => cur.filter((x) => x.id !== r.id));
    onBills(r.bills);
  }, [onBills]);

  const accepted = bills.filter((b) => b.accepted);
  const pending = bills.filter((b) => !b.accepted);
  const rec = planInputs?.recognition;
  return (
    <>
      <section className={`ep-drop${drag ? " ep-drop--over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); void upload(e.dataTransfer.files); }}>
        <span data-icon="receipt" data-size="24"></span>
        <div>
          <b>Drop your electricity bills here</b>
          <p className="eg-muted ep-small">PDF, as the DISCOM sends them, scanned or digital; a file may hold several months. ergPLAN reads the DISCOM, tariff category, voltage, contract demand and each month&apos;s units, and links every figure to the page it is printed on. Twelve months give the best profile; one is enough to start.</p>
        </div>
        <input ref={input} type="file" accept="application/pdf" multiple hidden onChange={(e) => e.target.files && void upload(e.target.files)} />
        <button className="eg-btn eg-btn--primary" onClick={() => input.current?.click()}>Choose files</button>
        {uploading > 0 && <span className="eg-muted"><span className="eg-dot eg-dot--live"></span> Uploading {uploading}…</span>}
      </section>
      {reads.length > 0 && <div className="ep-bills">{reads.map((r) => <ReadingCard key={r.id} initial={r} onDone={readDone} />)}</div>}
      {pending.length > 0 && <Note kind="warn">{pending.length} bill{pending.length > 1 ? "s need" : " needs"} a quick check below: confirm or correct the highlighted values, then the bill can be used.</Note>}
      {bills.length > 0 && <div className="ep-bills">{bills.map((b) => <BillReview key={b.id} bill={b} onChange={(nb) => onBills([nb])} />)}</div>}
      {rec && (
        <Note kind="ok">
          Recognised from your bill: <b>{rec.discom_name ?? rec.discom?.toUpperCase()}</b>{rec.state_name ? `, ${rec.state_name}` : ""}
          {rec.open_access !== "none_seen" ? `; open access: ${rec.open_access.replace("_", " ")}${rec.open_access_kinds.length ? ` (${rec.open_access_kinds.join(", ")})` : ""}` : "; no open access seen on the bill"}.
          {planInputs?.category_note ? <span> {planInputs.category_note[0].toUpperCase() + planInputs.category_note.slice(1)}.</span> : null}
          {rec.notes.map((n, i) => <span key={i}> {n}</span>)}
        </Note>
      )}
      {error && <p className="ep-error">{error}</p>}
      <div className="ep-divider"><span>{accepted.length ? "Check what the bills say, or correct it" : "or type the connection"}</span></div>
      <div className="ep-grid2">
        <Field label="DISCOM" required help="Your distribution company. Its tariff order sets your energy and demand charges; its state's regulator sets the open-access charges, losses and banking.">
          <select value={c.discom} onChange={(e) => { const dd = discoms.find((x) => x.id === e.target.value); upd({ discom: e.target.value, category: "", rate_block: "" }); if (dd) set((cur) => ({ ...cur, factory: { ...cur.factory, state: dd.state } })); }}>
            <option value="">Choose…</option>
            {inState.map((x) => <option key={x.id} value={x.id}>{x.name}{x.ready ? "" : " — tariff not yet sourced"}</option>)}
          </select>
        </Field>
        <Field label="Tariff category" required help="As printed on the bill (HV-2, HT I(A), LS…). It picks the tariff rows: energy charge, demand charge, time-of-day rates." hint={discom && !discom.ready ? "This DISCOM's tariff is not approved in ergPLAN yet; a plan cannot be computed for it." : undefined}>
          {catCodes.length ? (
            <select value={c.category} onChange={(e) => { const cc = cats.find((x) => x.code === e.target.value); upd({ category: e.target.value, voltage_kv: c.voltage_kv || cc?.usual_voltage_kv || "", rate_block: cc?.rate_block ?? "" }); }}>
              <option value="">Choose…</option>
              {catCodes.map((code) => <option key={code} value={code}>{code} — {cats.find((x) => x.code === code)?.label.split(" · ")[0]}</option>)}
            </select>
          ) : (
            <input value={c.category} onChange={(e) => upd({ category: e.target.value })} placeholder="as on the bill" />
          )}
        </Field>
        <Field label="Supply voltage" required unit="kV" help="11, 22, 33, 66, 132 kV… It decides the tariff row (rates differ by voltage), the wheeling losses applied to open-access power and the transmission charges.">
          <input inputMode="decimal" value={c.voltage_kv} onChange={(e) => upd({ voltage_kv: e.target.value })} placeholder={cat?.usual_voltage_kv ?? "e.g. 33"} />
        </Field>
        <Field label="Contract demand" required unit="kVA" help="The sanctioned demand on the bill. Demand charges are billed on at least a share of it, and open-access capacity cannot exceed it.">
          <input inputMode="decimal" value={c.contract_demand_kva} onChange={(e) => upd({ contract_demand_kva: e.target.value })} placeholder="e.g. 2500" />
        </Field>
        <Advanced>
          <div className="ep-grid2">
            <Field label="Consumer number" help="Shown on the plan and used to tell connections apart.">
              <input value={c.consumer_number} onChange={(e) => upd({ consumer_number: e.target.value })} />
            </Field>
            {(cats.some((x) => x.rate_block) || c.rate_block) && (
              <Field label="Supply schedule" help="Some orders split the schedule by supply area (urban/rural). The urban schedule is assumed unless the bill says otherwise.">
                <select value={c.rate_block} onChange={(e) => upd({ rate_block: e.target.value })}>
                  <option value="">as the bill says</option>
                  {[...new Set(cats.map((x) => x.rate_block).filter(Boolean))].map((rb) => <option key={rb as string} value={rb as string}>{rb}</option>)}
                </select>
              </Field>
            )}
          </div>
        </Advanced>
      </div>
    </>
  );
}

// 3. Consumption — from the bills, or typed as the year's units / month by month.
export function ConsumptionSection({ d, set, bills }: { d: Draft; set: Set; bills: BillOut[] }) {
  const k = d.consumption;
  const upd = (patch: Partial<Draft["consumption"]>) => set((cur) => ({ ...cur, consumption: { ...cur.consumption, ...patch } }));
  const accepted = bills.filter((b) => b.accepted);
  const modes: [Draft["consumption"]["mode"], string][] = [
    ["bills", `From my bills${accepted.length ? ` (${accepted.length})` : ""}`],
    ["annual", "The year's units"],
    ["months", "Month by month"],
  ];
  function addMonth() {
    const last = k.months[k.months.length - 1]?.month ?? k.year_end;
    const [y, m] = last.split("-").map(Number);
    const next = new Date(y, m, 1);
    upd({ months: [...k.months, { month: `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`, kwh: "", max_kva: "", bill_inr: "" }] });
  }
  return (
    <>
      <div className="eg-seg" role="group" aria-label="Where the consumption comes from">
        {modes.map(([m, label]) => <button key={m} aria-pressed={k.mode === m} onClick={() => upd({ mode: m })} disabled={m === "bills" && accepted.length === 0} title={m === "bills" && accepted.length === 0 ? "Upload and accept a bill first" : undefined}>{label}</button>)}
      </div>
      {k.mode === "bills" && (
        <Note kind="ok">Each accepted bill gives its month&apos;s units, time-of-day split, recorded demand and amount, every figure linked to its page. ergPLAN fills the other months from the industry pattern and marks them as estimates. The more months, the truer the year.</Note>
      )}
      {k.mode === "annual" && (
        <div className="ep-grid2">
          <Field label="Units in the last twelve months" required unit="kWh" help="Add up twelve bills, or take the figure from your energy audit. ergPLAN spreads it over the months by working days and marks each month as an estimate; replace them with bills when you have them.">
            <input inputMode="numeric" value={k.annual_kwh} onChange={(e) => upd({ annual_kwh: e.target.value })} placeholder="e.g. 9600000" />
          </Field>
          <Field label="Last month of the year" help="The twelve months end here. Default: last month.">
            <input type="month" value={k.year_end} onChange={(e) => upd({ year_end: e.target.value })} />
          </Field>
        </div>
      )}
      {k.mode === "months" && (
        <div className="ep-months">
          <table className="ep-table">
            <thead><tr><th>Month</th><th className="num">Units (kWh)</th><th className="num">Max demand (kVA)</th><th className="num">Bill (₹)</th><th></th></tr></thead>
            <tbody>
              {k.months.map((m, i) => (
                <tr key={i}>
                  <td><span className="eg-input"><input type="month" value={m.month} onChange={(e) => upd({ months: k.months.map((x, j) => (j === i ? { ...x, month: e.target.value } : x)) })} /></span></td>
                  <td className="num"><span className="eg-input"><input inputMode="numeric" value={m.kwh} onChange={(e) => upd({ months: k.months.map((x, j) => (j === i ? { ...x, kwh: e.target.value } : x)) })} /></span></td>
                  <td className="num"><span className="eg-input"><input inputMode="decimal" value={m.max_kva} onChange={(e) => upd({ months: k.months.map((x, j) => (j === i ? { ...x, max_kva: e.target.value } : x)) })} /></span></td>
                  <td className="num"><span className="eg-input"><input inputMode="numeric" value={m.bill_inr} onChange={(e) => upd({ months: k.months.map((x, j) => (j === i ? { ...x, bill_inr: e.target.value } : x)) })} /></span></td>
                  <td><button className="eg-btn eg-btn--ghost eg-btn--sm" aria-label="Remove month" onClick={() => upd({ months: k.months.filter((_, j) => j !== i) })}>×</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <button className="eg-btn eg-btn--ghost eg-btn--sm" onClick={addMonth}>+ Add a month</button>
        </div>
      )}
      <div className="ep-grid2">
        <Field label="Recorded maximum demand" unit="kVA" help="The highest demand the meter recorded in a typical month (on the bill as MD or RMD). It shapes the peaks of the profile and the demand charges. Leave blank to use the bills' figures or the contract demand.">
          <input inputMode="decimal" value={k.max_demand_kva} onChange={(e) => upd({ max_demand_kva: e.target.value })} placeholder="e.g. 2300" />
        </Field>
        <Field label="Power factor" help="Average power factor on the bill (0.90–0.99 for most industry). Converts kWh to the kVAh many DISCOMs bill. 0.95 is assumed if blank.">
          <input inputMode="decimal" value={k.power_factor} onChange={(e) => upd({ power_factor: e.target.value })} placeholder="0.95" />
        </Field>
      </div>
    </>
  );
}
