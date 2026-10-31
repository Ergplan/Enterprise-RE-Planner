"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { analystFetch, getAnalyst } from "@/lib/analyst";
import { FAMILY_LABEL } from "@/lib/rulebook";

type Draft = {
  version_id: string | null;
  family: string;
  accepted: number;
  rejected: { row: Record<string, unknown>; reasons: string[] }[];
  not_found: string[];
  notes: string[];
};

function parsePages(text: string): number[] {
  const out: number[] = [];
  for (const part of text.split(",").map((s) => s.trim()).filter(Boolean)) {
    const [a, b] = part.split(/[-–]/).map((x) => Number(x.trim()));
    if (Number.isFinite(a)) for (let p = a; p <= (Number.isFinite(b) ? b : a); p++) out.push(p);
  }
  return out;
}

// Reads the chosen pages of this document into a draft rulebook (OpenAI reader + grounding check).
export function ReadPanel({ documentId, defaultPages, jurisdictions }: { documentId: string; defaultPages: string; jurisdictions: string[] }) {
  const [family, setFamily] = useState("tariff_schedule");
  const [jur, setJur] = useState(jurisdictions[0] ?? "");
  const [pages, setPages] = useState(defaultPages);
  const [focus, setFocus] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Draft | null>(null);
  const [error, setError] = useState("");
  const [analyst, setAnalyst] = useState("");
  useEffect(() => setAnalyst(getAnalyst()), []);

  async function read() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(await analystFetch<Draft>("/regreader/direct", {
        method: "POST",
        body: JSON.stringify({ document_id: documentId, family, jurisdiction_id: jur, pages: parsePages(pages), focus }),
      }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="eg-card">
      <div className="eg-overline" style={{ marginBottom: 12 }}>Read into a rulebook</div>
      {!analyst && <p className="eg-muted" style={{ fontSize: 13 }}>Set your analyst email on any rulebook page first.</p>}
      <div style={{ display: "grid", gap: 10 }}>
        <label className="eg-field"><span className="eg-field__label">Family</span>
          <span className="eg-input"><select value={family} onChange={(e) => setFamily(e.target.value)}>
            {Object.entries(FAMILY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></span></label>
        <label className="eg-field"><span className="eg-field__label">For (DISCOM or state)</span>
          <span className="eg-input"><select value={jur} onChange={(e) => setJur(e.target.value)}>
            {jurisdictions.map((j) => <option key={j} value={j}>{j}</option>)}
          </select></span></label>
        <label className="eg-field"><span className="eg-field__label">PDF pages (e.g. 387-388, 315)</span>
          <span className="eg-input"><input value={pages} onChange={(e) => setPages(e.target.value)} /></span></label>
        <label className="eg-field"><span className="eg-field__label">What to read</span>
          <span className="eg-input"><input value={focus} placeholder="HV-2 urban schedule, approved rates only" onChange={(e) => setFocus(e.target.value)} /></span></label>
        <button className="eg-btn eg-btn--primary" disabled={busy || !analyst || !pages} onClick={read}>
          {busy ? "Reading…" : "Read pages"}
        </button>
      </div>
      {error && <p className="eg-chip eg-chip--negative" style={{ marginTop: 12 }}>{error}</p>}
      {result && (
        <div style={{ marginTop: 16, fontSize: 13 }}>
          <p><b>{result.accepted}</b> rows passed the checks; <b>{result.rejected.length}</b> were rejected.</p>
          {result.version_id && <Link className="eg-btn eg-btn--ghost eg-btn--sm" href={`/rulebooks/${result.version_id}`}>Review the draft</Link>}
          {result.rejected.map((r, i) => (
            <p key={i} className="eg-muted">{String(r.row.label ?? "row")}: {r.reasons.join("; ")}</p>
          ))}
          {result.not_found.length > 0 && <p className="eg-muted">Not on these pages: {result.not_found.join("; ")}</p>}
        </div>
      )}
    </section>
  );
}
