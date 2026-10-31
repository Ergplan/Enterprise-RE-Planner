"use client";

import { useEffect, useState } from "react";
import { getAnalyst } from "@/lib/analyst";
import type { PlanOut } from "@/lib/plan";

// The jouleWise view: every assumption, rule version, run pin and margin. Fetched with the analyst's
// headers; the API refuses it to anyone else.
export function AnalystView({ token }: { token: string }) {
  const [who, setWho] = useState("");
  const [d, setD] = useState<PlanOut | null>(null);
  const [error, setError] = useState("");
  useEffect(() => setWho(getAnalyst()), []);
  if (!who) return null;
  async function load() {
    const r = await fetch(`/api/p/${token}?view=analyst`, { headers: { "X-Ergplan-Actor": who, "X-Ergplan-Role": "analyst" } });
    if (!r.ok) {
      setError(`${r.status}`);
      return;
    }
    setD((await r.json()) as PlanOut);
  }
  return (
    <section className="eg-card ep-panel ep-noprint">
      <div className="ep-row">
        <button className="eg-btn eg-btn--ghost eg-btn--sm" onClick={() => (d ? setD(null) : load())}>{d ? "Client view" : "jouleWise view"}</button>
        <span className="eg-muted ep-small">Signed in as {who}</span>
      </div>
      {error && <p className="ep-error">{error}</p>}
      {d && (
        <>
          <div className="eg-overline" style={{ margin: "12px 0 6px" }}>Assumptions in this plan</div>
          <ul className="ep-list ep-small">{d.assumptions.map((a) => <li key={a.note}>{a.note}</li>)}</ul>
          {d.scenarios.map((s) => {
            const a = (s.analyst ?? {}) as { pins?: Record<string, unknown>; solver?: Record<string, unknown>; resettle?: { agrees: boolean; max_diff_kwh: string; solver_objective_inr: string; resettled_cost_inr: string }; rule_versions?: { id: string; family: string; jurisdiction: string; version: number; status: string; title: string | null; approved_by: string | null }[] };
            return (
              <div key={s.scenario_id} style={{ marginTop: 12 }}>
                <div className="eg-overline">{s.name}</div>
                <p className="ep-small">
                  Run {s.run_id.slice(0, 8)} · {String(a.pins?.solver ?? "")} · gap {String(a.solver?.gap ?? 0)} · {String(a.solver?.seconds ?? "")} s ·
                  judge {a.resettle?.agrees ? "agrees" : "disagrees"} ({a.resettle?.max_diff_kwh} kWh) · solver ₹{a.resettle?.solver_objective_inr} vs re-settled ₹{a.resettle?.resettled_cost_inr} ·
                  load profile {String(a.pins?.load_profile_version ?? "")} · as of {String(a.pins?.as_of ?? "")}
                </p>
                <table className="ep-table ep-small"><tbody>
                  {(a.rule_versions ?? []).map((v) => (
                    <tr key={v.id}><td>{v.jurisdiction.toUpperCase()} · {v.family}</td><td>v{v.version} ({v.status})</td><td>{v.title}</td><td>{v.approved_by}</td></tr>
                  ))}
                </tbody></table>
              </div>
            );
          })}
        </>
      )}
    </section>
  );
}
