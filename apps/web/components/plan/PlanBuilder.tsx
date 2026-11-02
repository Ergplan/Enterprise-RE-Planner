"use client";

import { useCallback, useEffect, useState } from "react";
import { clientFetch } from "@/lib/intake";
import type { PlanOut } from "@/lib/plan";
import { crore } from "@/lib/runs";

// Journey step 6 for the client: size the standard plan (no analyst needed), watch it settle, share it.
export function PlanBuilder({ connectionId, initial }: { connectionId: string; initial: PlanOut }) {
  const [plan, setPlan] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState<{ path: string; url: string } | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setPlan(await clientFetch<PlanOut>(`/connections/${connectionId}/plan`));
  }, [connectionId]);

  useEffect(() => {
    if (!plan.pending_runs) return;
    const t = setInterval(() => void refresh().catch(() => undefined), 4000);
    return () => clearInterval(t);
  }, [plan.pending_runs, refresh]);

  async function build() {
    setBusy(true);
    setError("");
    try {
      await clientFetch(`/connections/${connectionId}/plan`, { method: "POST" });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function share() {
    setError("");
    try {
      setLink(await clientFetch<{ path: string; url: string }>(`/connections/${connectionId}/share`, { method: "POST" }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const done = plan.scenarios.length;
  return (
    <section className="eg-card ep-panel">
      {done === 0 && !plan.pending_runs && (
        <>
          <p>We size three options for your site — captive solar; a hybrid supply with a battery; rooftop, solar and a battery — over a year of 15-minute blocks, and settle each under your DISCOM&apos;s rules.</p>
          <button className="eg-btn eg-btn--primary" disabled={busy} onClick={build}>{busy ? "Starting…" : "Build my plan"}</button>
        </>
      )}
      {plan.pending_runs > 0 && <p className="ep-plan-status">Working out your plan: {done} of {done + plan.pending_runs} options settled. This takes a minute or two each.</p>}
      {done > 0 && (
        <table className="ep-table">
          <tbody>
            {plan.scenarios.map((s) => (
              <tr key={s.scenario_id}><td>{s.name}{s.scenario_id === plan.recommended ? " (recommended)" : ""}</td><td className="num">{crore(s.summary.annual.saving)} a year</td></tr>
            ))}
          </tbody>
        </table>
      )}
      {done > 0 && (
        <div className="ep-row" style={{ marginTop: 12 }}>
          <button className="eg-btn eg-btn--primary" onClick={share}>Share my plan</button>
          <a className="eg-btn eg-btn--ghost" href={`/plan/audit?c=${connectionId}`}>Audit the chain and check your working</a>
          {link && <a className="ep-share-link" href={link.path}>{link.url}</a>}
        </div>
      )}
      {error && <p className="ep-error">{error}</p>}
    </section>
  );
}
