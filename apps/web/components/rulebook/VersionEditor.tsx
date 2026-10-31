"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { analystFetch, getAnalyst, setAnalyst } from "@/lib/analyst";
import { describe, FAMILY_LABEL, leaves, scopeChips, setAt, type Row, type VersionDetail } from "@/lib/rulebook";
import { Citation } from "./Citation";

type Props = { initial: VersionDetail; bodySchema?: Record<string, unknown> };

export function VersionEditor({ initial, bodySchema }: Props) {
  const [detail, setDetail] = useState(initial);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [analyst, setAnalystState] = useState("");
  const router = useRouter();
  const v = detail.version;
  const draft = v.status === "draft";

  useEffect(() => setAnalystState(getAnalyst()), []);

  async function act(label: string, path: string, method = "POST", body?: unknown) {
    setBusy(label);
    setError("");
    try {
      const d = await analystFetch<VersionDetail>(path, { method, body: body ? JSON.stringify(body) : undefined });
      if (d.version.id !== v.id) router.push(`/rulebooks/${d.version.id}`);
      else setDetail(d);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  const passed = detail.golden.filter((g) => g.passed).length;
  return (
    <>
      <section className="eg-glass" style={{ padding: "var(--space-6)" }}>
        <div className="eg-card__head">
          <div>
            <h1 className="eg-card__title" style={{ fontSize: 26 }}>
              {FAMILY_LABEL[v.family] ?? v.family} · {v.jurisdiction_id.toUpperCase()} · v{v.version}
            </h1>
            <p className="eg-card__sub">{v.title}</p>
          </div>
          <span className={`eg-chip ${v.status === "approved" ? "eg-chip--accent" : v.status === "draft" ? "eg-chip--warning" : ""}`}>
            {v.status}
          </span>
        </div>
        <dl className="ep-kv">
          <dt>In force from</dt>
          <dd>{v.effective_from}{v.effective_to ? ` to ${v.effective_to}` : ""}</dd>
          <dt>Origin</dt>
          <dd>{v.origin.replaceAll("_", " ")}</dd>
          <dt>Created by</dt>
          <dd>{v.created_by}</dd>
          {v.approved_by && (
            <>
              <dt>Approved by</dt>
              <dd>{v.approved_by}</dd>
            </>
          )}
          <dt>Golden tests</dt>
          <dd>
            {detail.golden.length === 0 ? "None written for this family yet" : `${passed} of ${detail.golden.length} passed`}
          </dd>
        </dl>
        <div className="ep-row" style={{ marginTop: "var(--space-5)" }}>
          <label className="eg-field" style={{ minWidth: 260 }}>
            <span className="eg-field__label">Analyst (your email)</span>
            <span className="eg-input">
              <input
                value={analyst}
                placeholder="name@joulewise.in"
                onChange={(e) => {
                  setAnalystState(e.target.value);
                  setAnalyst(e.target.value);
                }}
              />
            </span>
          </label>
          {draft && (
            <>
              <button className="eg-btn eg-btn--ghost" disabled={!!busy || !analyst} onClick={() => act("golden", `/rulebooks/versions/${v.id}/golden`)}>
                {busy === "golden" ? "Running…" : "Run golden tests"}
              </button>
              <button className="eg-btn eg-btn--primary" disabled={!!busy || !analyst} onClick={() => act("approve", `/rulebooks/versions/${v.id}/approve`)}>
                {busy === "approve" ? "Approving…" : "Approve version"}
              </button>
              <button className="eg-btn eg-btn--ghost" disabled={!!busy || !analyst} onClick={() => act("reject", `/rulebooks/versions/${v.id}/reject`)}>
                Reject
              </button>
            </>
          )}
          {!draft && (
            <button className="eg-btn eg-btn--ghost" disabled={!!busy || !analyst} onClick={() => act("dup", `/rulebooks/versions/${v.id}/duplicate`)}>
              {busy === "dup" ? "Copying…" : "Duplicate into a draft"}
            </button>
          )}
        </div>
        {error && <p className="eg-chip eg-chip--negative" style={{ marginTop: 12 }}>{error}</p>}
      </section>

      {detail.rows.map((row) => (
        <RowCard key={row.id} row={row} versionId={v.id} editable={draft && !!analyst} bodySchema={bodySchema}
          onSaved={setDetail} onError={setError} />
      ))}

      {detail.golden.length > 0 && (
        <section className="eg-card">
          <div className="eg-card__head">
            <h2 className="eg-card__title"><span data-icon="check" data-size="20"></span>Golden tests</h2>
            <p className="eg-card__sub">Written from the page text by a person, independently of the reader. Approval needs all of them to pass.</p>
          </div>
          <table className="ep-table">
            <thead><tr><th>Test</th><th>Expected</th><th>Actual</th><th>Result</th></tr></thead>
            <tbody>
              {detail.golden.map((g) => (
                <tr key={g.name}>
                  <td>{g.name}</td>
                  <td className="eg-mono">{JSON.stringify(g.expect)}</td>
                  <td className="eg-mono">{g.actual ? JSON.stringify(g.actual) : "—"}</td>
                  <td>
                    {g.passed === null ? <span className="eg-chip">Not run</span> : g.passed ? <span className="eg-chip eg-chip--accent">Passed</span> : <span className="eg-chip eg-chip--negative">Failed</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}

function RowCard({ row, versionId, editable, bodySchema, onSaved, onError }: {
  row: Row; versionId: string; editable: boolean; bodySchema?: Record<string, unknown>;
  onSaved: (d: VersionDetail) => void; onError: (m: string) => void;
}) {
  const [body, setBody] = useState(row.body);
  const [json, setJson] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify(body) !== JSON.stringify(row.body);
  const review = row.review as { reader?: string; model?: string; decision?: string; note?: string; by?: string };

  async function save(next: Record<string, unknown>) {
    setSaving(true);
    try {
      const d = await analystFetch<VersionDetail>(`/rulebooks/versions/${versionId}/rows/${row.id}`, {
        method: "PUT",
        body: JSON.stringify({ label: row.label, scope: row.scope, body: next, source_ref: row.source_ref,
          field_refs: Object.keys(row.field_refs ?? {}).length ? row.field_refs : undefined,
          review: { decision: "edited" } }),
      });
      onSaved(d);
      setJson(null);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="eg-card ep-rule">
      <div className="eg-card__head">
        <div>
          <h3 className="eg-card__title" style={{ fontSize: 18 }}>{row.label ?? "Rule"}</h3>
          <div className="ep-row" style={{ marginTop: 8 }}>
            {scopeChips(row.scope).map((c) => <span key={c} className="eg-chip">{c}</span>)}
          </div>
        </div>
        {review?.reader && <span className="eg-chip eg-chip--mono">{review.reader.replaceAll("_", " ")}{review.model ? ` · ${review.model}` : ""}</span>}
      </div>
      <div className="ep-rule__grid">
        <table className="ep-table">
          <tbody>
            {leaves(body).map(({ pointer, value }) => {
              const desc = describe(bodySchema, pointer);
              const cite = row.field_refs?.[pointer];
              return (
                <tr key={pointer}>
                  <td style={{ width: "42%" }}>
                    <div className="eg-mono">{pointer.slice(1).replaceAll("/", " › ")}</div>
                    {desc && <div className="eg-muted" style={{ fontSize: 12 }}>{desc}</div>}
                  </td>
                  <td>
                    {editable && (typeof value === "string" || typeof value === "number") ? (
                      <span className="eg-input">
                        <input value={String(value)} onChange={(e) => setBody(setAt(body, pointer, e.target.value))} />
                      </span>
                    ) : (
                      <b>{value === null ? "—" : String(value)}</b>
                    )}
                    {cite && <Citation cite={cite} compact />}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div>
          <div className="eg-overline" style={{ marginBottom: 8 }}>Where this is written</div>
          <Citation cite={row.source_ref} />
          {review?.note && <p className="eg-muted" style={{ fontSize: 12, marginTop: 12 }}>Review note: {review.note}</p>}
        </div>
      </div>
      {editable && (
        <div className="ep-row" style={{ marginTop: 12 }}>
          <button className="eg-btn eg-btn--primary eg-btn--sm" disabled={!dirty || saving} onClick={() => save(body)}>
            {saving ? "Saving…" : "Save row"}
          </button>
          <button className="eg-btn eg-btn--ghost eg-btn--sm" onClick={() => setJson(json === null ? JSON.stringify(body, null, 2) : null)}>
            {json === null ? "Edit as JSON" : "Close JSON"}
          </button>
          <Link className="ep-cite" href={`/documents/${row.source_ref.document_id}?page=${row.source_ref.page}`}>Check against the page</Link>
        </div>
      )}
      {json !== null && (
        <div style={{ marginTop: 12 }}>
          <textarea className="ep-json" value={json} onChange={(e) => setJson(e.target.value)} rows={10} />
          <button className="eg-btn eg-btn--ghost eg-btn--sm" onClick={() => { try { save(JSON.parse(json)); } catch { onError("That is not valid JSON"); } }}>
            Save JSON
          </button>
        </div>
      )}
    </section>
  );
}
