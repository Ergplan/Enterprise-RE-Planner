"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  CATEGORIES,
  clientFetch,
  DAYS,
  monthLabel,
  stated,
  type ShapeOut,
  type SiteIntake,
} from "@/lib/intake";
import { AssetsEditor } from "./AssetsEditor";
import { FactRow, ProvenanceChip } from "./FactChip";

// the open access the consumer already takes (SiteIntake.open_access)
const OPEN_ACCESS_CHOICES: [string, string][] = [
  ["none", "None"],
  ["captive", "Captive"],
  ["group_captive", "Group captive"],
  ["third_party", "Third-party open access"],
  ["exchange", "Power exchange"],
  ["geoa", "Green energy open access (GEOA)"],
  ["green_tariff", "Green tariff from the DISCOM"],
  ["open_access", "Open access, kind not known"],
];

type BuildOut = { connection_id: string; warnings: string[]; load_profile_version: number };

// The intake as ergPLAN understood it: every value with where it came from. Editing a value makes it
// "you said". Building saves the site and synthesises the 15-minute load profile.
export function IntakeReview({ initial, connectionId, submitLabel = "Save and build my load profile" }: {
  initial: SiteIntake;
  connectionId?: string;
  submitLabel?: string;
}) {
  const router = useRouter();
  const [si, setSi] = useState<SiteIntake>(initial);
  const [shapes, setShapes] = useState<ShapeOut[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);

  useEffect(() => {
    clientFetch<ShapeOut[]>("/intake/shapes").then(setShapes).catch(() => setShapes([]));
  }, []);

  const set = <K extends keyof SiteIntake>(k: K, v: SiteIntake[K]) => setSi((s) => ({ ...s, [k]: v }));

  async function build() {
    setBusy(true);
    setError("");
    try {
      const out = await clientFetch<BuildOut>("/sites", { method: "POST", body: JSON.stringify({ intake: si, connection_id: connectionId }) });
      setWarnings(out.warnings);
      if (connectionId) router.refresh();
      else router.push(`/plan/site?c=${out.connection_id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const shape = shapes.find((s) => s.id === si.industry_shape.value);
  return (
    <section className="eg-glass ep-panel">
      <div className="eg-card__head">
        <div>
          <h2 className="eg-card__title">What we understood</h2>
          <p className="eg-card__sub">Values from your bill link to its page. Anything assumed is marked; change it if it is wrong.</p>
        </div>
      </div>
      <div className="ep-facts">
        <FactRow label="Company" fact={si.client_name} onEdit={(v) => set("client_name", stated(v))} />
        <FactRow label="Site" fact={si.site_name} onEdit={(v) => set("site_name", stated(v))} />
        <FactRow label="DISCOM" fact={si.discom} render={(v) => String(v).toUpperCase()} />
        <FactRow label="State" fact={si.state} />
        <div className="ep-fact">
          <div className="ep-fact__label">Tariff category</div>
          <div className="ep-fact__value">
            <span className="eg-input ep-fact__input">
              <select aria-label="Tariff category" value={si.category.value} onChange={(e) => set("category", stated(e.target.value))}>
                {[...new Set([si.category.value, ...(CATEGORIES[si.state.value] ?? [])])].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </span>
          </div>
          <div><ProvenanceChip provenance={si.category.provenance} refx={si.category.ref} /></div>
          {si.category.provenance === "assumption" && <div className="ep-fact__note eg-muted">{si.category.ref?.note}</div>}
        </div>
        <div className="ep-fact">
          <div className="ep-fact__label">Open access today</div>
          <div className="ep-fact__value">
            <span className="eg-input ep-fact__input">
              <select
                aria-label="Open access today"
                value={si.open_access?.value ?? ""}
                onChange={(e) => setSi((cur) => ({ ...cur, open_access: e.target.value ? stated(e.target.value) : null }))}
              >
                <option value="">not stated</option>
                {OPEN_ACCESS_CHOICES.map(([v, label]) => (
                  <option key={v} value={v}>{label}</option>
                ))}
              </select>
            </span>
          </div>
          <div>{si.open_access && <ProvenanceChip provenance={si.open_access.provenance} refx={si.open_access.ref} />}</div>
          <div className="ep-fact__note eg-muted">New green power is settled under this arrangement unless you choose otherwise.</div>
        </div>
        <FactRow label="Supply voltage" unit="kV" fact={si.voltage_kv} onEdit={(v) => set("voltage_kv", stated(v))} />
        <FactRow label="Contract demand" unit="kVA" fact={si.contract_demand_kva} onEdit={(v) => set("contract_demand_kva", stated(v))} />
        <div className="ep-fact">
          <div className="ep-fact__label">How the plant runs</div>
          <div className="ep-fact__value">
            <span className="eg-input ep-fact__input">
              <select aria-label="Operating pattern" value={si.industry_shape.value} onChange={(e) => {
                const s = shapes.find((x) => x.id === e.target.value);
                setSi((cur) => ({
                  ...cur,
                  industry_shape: stated(e.target.value),
                  weekly_off: s ? stated([0, 1, 2, 3, 4, 5, 6].filter((d) => !s.working_days.includes(d))) : cur.weekly_off,
                }));
              }}>
                {(shapes.length ? shapes : [{ id: si.industry_shape.value, name: si.industry_shape.value }]).map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </span>
          </div>
          <div><ProvenanceChip provenance={si.industry_shape.provenance} refx={si.industry_shape.ref} /></div>
          {shape?.note && <div className="ep-fact__note eg-muted">{shape.note}</div>}
        </div>
        <div className="ep-fact">
          <div className="ep-fact__label">Weekly off</div>
          <div className="ep-fact__value ep-row">
            {DAYS.map((d, i) => (
              <label key={d} className="ep-day">
                <input type="checkbox" checked={si.weekly_off.value.includes(i)} onChange={(e) => {
                  const cur = si.weekly_off.value.filter((x) => x !== i);
                  set("weekly_off", stated(e.target.checked ? [...cur, i].sort() : cur));
                }} />
                {d}
              </label>
            ))}
          </div>
          <div><ProvenanceChip provenance={si.weekly_off.provenance} refx={si.weekly_off.ref} /></div>
        </div>
      </div>

      <h3 className="eg-overline" style={{ margin: "var(--space-6) 0 var(--space-3)" }}>Months</h3>
      <table className="ep-table">
        <thead>
          <tr><th>Month</th><th className="num">Energy</th><th className="num">Max demand</th><th className="num">Power factor</th><th>Source</th></tr>
        </thead>
        <tbody>
          {si.months.map((m) => (
            <tr key={m.month}>
              <td>{monthLabel(m.month)}</td>
              <td className="num">{Number(m.energy.value).toLocaleString("en-IN")} {m.energy_unit}</td>
              <td className="num">{m.max_kva ? `${Number(m.max_kva.value).toLocaleString("en-IN")} kVA` : "—"}</td>
              <td className="num">{m.power_factor?.value ?? "—"}</td>
              <td><ProvenanceChip provenance={m.energy.provenance} refx={m.energy.ref} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {si.months.length < 12 && (
        <p className="eg-muted ep-note">
          {si.months.length} of 12 months. The other months are estimated from these and marked as assumed; add more bills for a better profile.
        </p>
      )}
      {connectionId && (
        <>
          <h3 className="eg-overline" style={{ margin: "var(--space-6) 0 var(--space-3)" }}>Generation and storage already on site</h3>
          <AssetsEditor assets={si.assets} onChange={(a) => set("assets", a)} />
        </>
      )}
      {warnings.length > 0 && <ul className="ep-warn">{warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
      {error && <p className="ep-error">{error}</p>}
      <div className="ep-row" style={{ marginTop: "var(--space-6)" }}>
        <button className="eg-btn eg-btn--primary" disabled={busy} onClick={build}>{busy ? "Building…" : submitLabel}</button>
      </div>
    </section>
  );
}
