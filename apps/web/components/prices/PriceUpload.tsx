"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getAnalyst } from "@/lib/analyst";

type UploadOut = { vintage: { id: string; segment: string; rows: number; date_from: string; date_to: string }; conflicts: number; missing_blocks: number; skipped: string[] };

const SEGMENTS = ["", "dam", "rtm", "gdam", "gtam", "hpdam", "tam"];

// Analyst: upload one IEX market-snapshot file (xlsx or csv). One file is one vintage; a file that
// overlaps a loaded vintage of its segment is refused unless "replace" is ticked.
export function PriceUpload() {
  const router = useRouter();
  const file = useRef<HTMLInputElement>(null);
  const [segment, setSegment] = useState("");
  const [replace, setReplace] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [analyst, setAnalyst] = useState("");
  useEffect(() => setAnalyst(getAnalyst()), []);

  async function upload() {
    const f = file.current?.files?.[0];
    if (!f) return;
    setBusy(true);
    setError("");
    setMsg("");
    const fd = new FormData();
    fd.append("file", f);
    if (segment) fd.append("segment", segment);
    if (replace) fd.append("replace", "true");
    try {
      const r = await fetch("/api/prices", { method: "POST", body: fd, headers: { "X-Ergplan-Actor": analyst, "X-Ergplan-Role": "analyst" } });
      const body = await r.json();
      if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : body.detail?.message ?? `${r.status}`);
      const out = body as UploadOut;
      setMsg(`${out.vintage.segment.toUpperCase()}: ${out.vintage.rows.toLocaleString("en-IN")} blocks from ${out.vintage.date_from} to ${out.vintage.date_to}` +
        `${out.missing_blocks ? `, ${out.missing_blocks} blocks missing in that range` : ""}${out.conflicts ? `, ${out.conflicts} conflicting duplicates resolved to the latest` : ""}.`);
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="eg-card ep-panel">
      <div className="eg-overline" style={{ marginBottom: 12 }}>Upload an IEX file</div>
      {!analyst && <p className="eg-muted" style={{ fontSize: 13 }}>Set your analyst email on any rulebook page first.</p>}
      <div className="ep-form">
        <label className="eg-field"><span className="eg-field__label">File (xlsx or csv)</span>
          <span className="eg-input"><input ref={file} type="file" accept=".xlsx,.csv" /></span></label>
        <label className="eg-field"><span className="eg-field__label">Segment</span>
          <span className="eg-input"><select value={segment} onChange={(e) => setSegment(e.target.value)}>
            {SEGMENTS.map((s) => <option key={s} value={s}>{s ? s.toUpperCase() : "From the file name"}</option>)}
          </select></span></label>
        <label className="ep-day" style={{ alignSelf: "end" }}>
          <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} /> Replace overlapping prices
        </label>
      </div>
      <div className="ep-row" style={{ marginTop: "var(--space-4)" }}>
        <button className="eg-btn eg-btn--primary" disabled={busy || !analyst} onClick={upload}>{busy ? "Loading…" : "Upload"}</button>
      </div>
      {msg && <p className="eg-muted ep-note">{msg}</p>}
      {error && <p className="ep-error">{error}</p>}
    </section>
  );
}
