"use client";

import { useState } from "react";
import { clientFetch, fieldLabel, monthLabel, type BillOut } from "@/lib/intake";

const STATUS: Record<string, string> = {
  passed: "Read and verified",
  confirmed: "Confirmed",
  needs_review: "Please check a few values",
  unreadable: "Could not be read",
  not_a_bill: "Not an electricity bill",
};

// One bill as billx read it. Values billx could not verify wait for a one-click confirmation (or a
// correction); each confirmation is recorded with who made it (bill_confirmations).
export function BillReview({ bill, onChange }: { bill: BillOut; onChange: (b: BillOut) => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [error, setError] = useState("");

  async function confirm(path: string, value: string | null) {
    setBusy(path);
    setError("");
    try {
      onChange(await clientFetch<BillOut>(`/bills/${bill.id}/confirm`, { method: "POST", body: JSON.stringify({ path, value }) }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const shown = bill.fields.filter((f) => f.required || f.value !== null);
  const pending = bill.outstanding.length;
  return (
    <article className="eg-card ep-bill">
      <div className="eg-card__head">
        <div>
          <h3 className="eg-card__title">{bill.bill_month ? monthLabel(bill.bill_month) : bill.filename}</h3>
          <p className="eg-card__sub">
            {bill.discom ? bill.discom.toUpperCase() : "DISCOM not recognised"} · {bill.filename}
          </p>
        </div>
        <div className="ep-row">
          <span className={`eg-chip ${bill.accepted ? "eg-chip--accent" : "eg-chip--warning"}`}>
            {bill.accepted ? (bill.accepted_by === "bill_confirmations" ? "Confirmed by you" : STATUS[bill.status] ?? bill.status) : `${pending} to check`}
          </span>
          <a className="eg-btn eg-btn--sm eg-btn--primary" href={`/plan/intake/bill/${bill.id}`}>
            <span data-icon="eye" data-size="14"></span>Reading view
          </a>
          <a className="ep-cite" href={`/api${bill.file_url}`} target="_blank" rel="noreferrer">
            <span data-icon="file" data-size="14"></span>Open the bill
          </a>
        </div>
      </div>
      <table className="ep-table">
        <tbody>
          {shown.map((f) => (
            <tr key={f.path} className={f.needs_confirmation ? "ep-attn" : undefined}>
              <td>{fieldLabel(f.path, bill.tod_slots)}</td>
              <td className="num">
                {f.needs_confirmation ? (
                  <span className="eg-input ep-fact__input">
                    <input aria-label={fieldLabel(f.path, bill.tod_slots)} defaultValue={f.value ?? ""}
                      onChange={(e) => setEdits({ ...edits, [f.path]: e.target.value })} />
                  </span>
                ) : (
                  <b>{f.value ?? "—"}</b>
                )}
                {f.unit && f.value !== null && <span className="eg-muted"> {f.unit}</span>}
              </td>
              <td className="nowrap">
                {f.needs_confirmation ? (
                  <button className="eg-btn eg-btn--sm eg-btn--accent" disabled={busy !== null}
                    onClick={() => confirm(f.path, (edits[f.path] ?? f.value ?? "").trim() || null)}>
                    {busy === f.path ? "Saving…" : edits[f.path] !== undefined && edits[f.path] !== f.value ? "Correct" : "Looks right"}
                  </button>
                ) : f.confirmed ? (
                  <span className="eg-chip eg-chip--accent">confirmed</span>
                ) : f.verification === "verified" ? (
                  <span className="eg-chip">verified{f.page ? ` · p. ${f.page}` : ""}</span>
                ) : (
                  <span className="eg-chip">{f.verification ?? "not printed"}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {bill.tod_slots.length > 0 && bill.tod_slots.every((s) => !s || !/\d{1,2}([:.]\d\d)?\s*(to|-|–)\s*\d{1,2}/i.test(s)) && (
        <p className="eg-muted ep-note">
          This bill names its time-of-day slots ({bill.tod_slots.join(", ")}) without their hours, so the month&apos;s total is used
          and the day&apos;s shape comes from your operating pattern.
        </p>
      )}
      {error && <p className="ep-error">{error}</p>}
    </article>
  );
}
