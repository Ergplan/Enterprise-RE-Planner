"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RefChips } from "@/components/cost/RefChips";
import { analystFetch } from "@/lib/analyst";
import {
  KIND_WORDS, STATUS_LABEL, STATUS_TONE, fmt, linesByKey,
  type AuditOut, type Chain, type ChainStep, type Proposal, type RerunOut, type WorkingLine,
} from "@/lib/audit";
import { clientFetch, type Ref } from "@/lib/intake";

type ScenarioChoice = { scenario_id: string; name: string };
const UNITS = ["INR/kWh", "paise/kWh", "percent", "INR/MW/month", "INR/kW/month", "INR", "kWh", "MWh", "kW", "MW"];

// The audit screen: every link from the generator's price to the saving, with its rate, its rule's page
// and, beside it, the client's own figure from their working and the difference the API computed. The chat
// reads an uploaded working against the chain; differences close by kind (your figure → the plan's input;
// a regulatory one → an analyst; a computed one → explained or accepted).
export function AuditScreen({ connectionId, initialChain, initialAudit, scenarios }: {
  connectionId: string; initialChain: Chain; initialAudit: AuditOut; scenarios: ScenarioChoice[];
}) {
  const [chain, setChain] = useState(initialChain);
  const [audit, setAudit] = useState(initialAudit);
  const [role, setRole] = useState("client");
  const [error, setError] = useState("");
  const [pending, setPending] = useState<RerunOut | null>(null);
  const scenario = chain.scenario_id;

  useEffect(() => {
    clientFetch<{ role: string }>("/auth/me").then((m) => setRole(m.role)).catch(() => undefined);
  }, []);

  const reload = useCallback(async (scenarioId: string = scenario) => {
    try {
      const q = `?scenario_id=${encodeURIComponent(scenarioId)}`;
      const [c, a] = await Promise.all([
        clientFetch<Chain>(`/connections/${connectionId}/chain${q}`),
        clientFetch<AuditOut>(`/connections/${connectionId}/audit${q}`),
      ]);
      setChain(c);
      setAudit(a);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, [connectionId, scenario]);

  // a run with the client's figures: poll until it is settled, then compare the open lines again
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(async () => {
      try {
        const r = await clientFetch<{ status: string }>(`/runs/${pending.run_id}`);
        if (r.status === "done") {
          clearInterval(t);
          await clientFetch(`/connections/${connectionId}/audit/refresh?scenario_id=${pending.scenario_id}`, { method: "POST" });
          setPending(null);
          await reload(pending.scenario_id);
        } else if (r.status.startsWith("failed")) {
          clearInterval(t);
          setPending(null);
          setError(`The run with your figures did not settle (${r.status}).`);
        }
      } catch {
        /* not visible until settled: keep polling */
      }
    }, 5000);
    return () => clearInterval(t);
  }, [pending, connectionId, reload]);

  const theirs = useMemo(() => linesByKey(audit.workings), [audit.workings]);
  const unmatched = audit.workings.flatMap((w) => w.lines.filter((l) => !l.chain_key));
  const choices = scenarios.some((s) => s.scenario_id === scenario) ? scenarios : [...scenarios, { scenario_id: scenario, name: chain.scenario }];

  async function act<T>(fn: () => Promise<T>): Promise<T | null> {
    setError("");
    try {
      const out = await fn();
      await reload();
      return out;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  }

  return (
    <div className="ep-audit">
      <div className="ep-audit__main">
        <section className="eg-card ep-panel">
          <div className="ep-row ep-audit__head">
            <label className="eg-field">
              <span className="eg-field__label">Scenario</span>
              <span className="eg-input">
                <select value={scenario} onChange={(e) => void reload(e.target.value)}>
                  {choices.map((s) => <option key={s.scenario_id} value={s.scenario_id}>{s.name}</option>)}
                </select>
              </span>
            </label>
            <div className="ep-stat">
              <span className="ep-stat__label">Saving for the year</span>
              <b className="ep-big">{fmt(chain.saving.value, "INR")}</b>
            </div>
            <div className="ep-small">
              Settled under <b>{chain.settlement_rule ?? "no approved settlement rule"}</b>
              {chain.settlement_ref && <RefChips refs={[chain.settlement_ref]} max={1} />}
            </div>
          </div>
          {pending && <p className="ep-note">Running the plan again with your figures ({pending.scenario})… the chain refreshes when it is settled.</p>}
          {error && <p className="ep-error">{error}</p>}
        </section>

        {chain.sources.filter((s) => s.landed.length > 0).map((s) => (
          <section key={s.id} className="eg-card ep-panel">
            <div className="eg-card__head">
              <div>
                <h2 className="eg-card__title">{s.label}: landed cost at your meter</h2>
                <p className="eg-card__sub">
                  {s.ownership ? s.ownership.replace("_", " ") : "own plant"}
                  {s.capacity && ` · ${fmt(s.capacity.value, s.capacity.unit)}`}
                  {s.slot && ` · ${s.slots_differ ? `time-of-day slot ${s.slot} shown (slots differ)` : "the same in every slot"}`}
                </p>
              </div>
              {s.landed_total && <div className="ep-source__total"><b>{fmt(s.landed_total.value, "INR/kWh")}</b><span className="eg-muted">/kWh</span></div>}
            </div>
            <ChainTable steps={s.landed} theirs={theirs} running />
            {Object.keys(s.gaps).length > 0 && (
              <ul className="ep-gaps">{Object.entries(s.gaps).map(([k, g]) => <li key={k}>{g}</li>)}</ul>
            )}
          </section>
        ))}

        <section className="eg-card ep-panel">
          <h2 className="eg-card__title">Energy for the year</h2>
          {chain.sources.map((s) => s.energy.length > 0 && (
            <div key={s.id}>
              <h3 className="eg-overline">{s.label}</h3>
              <ChainTable steps={s.energy} theirs={theirs} />
            </div>
          ))}
          <h3 className="eg-overline">The site</h3>
          <ChainTable steps={chain.energy} theirs={theirs} />
        </section>

        <section className="eg-card ep-panel">
          <h2 className="eg-card__title">Money for the year</h2>
          <ChainTable steps={chain.money} theirs={theirs} />
          {chain.notes.length > 0 && <ul className="ep-list ep-small">{chain.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
        </section>

        {unmatched.length > 0 && (
          <section className="eg-card ep-panel">
            <h2 className="eg-card__title">In your working, not in the plan</h2>
            <p className="eg-muted ep-small">Figures your working counts that the plan has no link for. Tell the assistant what each is; a charge the plan leaves out goes to an analyst.</p>
            <table className="ep-table">
              <tbody>{unmatched.map((l) => <tr key={l.id}><td>{l.label}</td><td className="num">{fmt(l.theirs, l.unit)}</td><td className="ep-small">“{l.quote}”</td></tr>)}</tbody>
            </table>
          </section>
        )}

        <Lines audit={audit} chain={chain} onAct={act} onRerun={setPending} />
        {role === "analyst" && <ProposalQueue proposals={audit.proposals} onAct={act} />}
      </div>

      <AuditChat connectionId={connectionId} scenarioId={scenario} audit={audit} onChanged={() => reload()} onRerun={setPending} />
    </div>
  );
}

// a computed figure carries the refs of every input: show its pages and one chip per other kind
function compactRefs(refs: Ref[]): Ref[] {
  const seen = new Set<string>();
  return refs.filter((r) => {
    if ((r.kind === "order" || r.kind === "regulation") && r.document_id) return true;
    if (seen.has(r.kind)) return false;
    seen.add(r.kind);
    return true;
  });
}

function ChainTable({ steps, theirs, running = false }: { steps: ChainStep[]; theirs: Record<string, WorkingLine>; running?: boolean }) {
  if (steps.length === 0) return <p className="eg-muted ep-small">Nothing settled here.</p>;
  return (
    <div className="ep-scroll">
      <table className="ep-table ep-chain">
        <thead>
          <tr>
            <th>Link</th><th className="num">Rate</th><th className="num">Effect</th>
            {running && <th className="num">Running total</th>}
            <th>Source</th><th className="num">Yours</th><th className="num">Difference</th><th></th>
          </tr>
        </thead>
        <tbody>
          {steps.map((st) => {
            const l = theirs[st.key];
            const total = st.kind === "total";
            return (
              <tr key={st.key} className={total ? "ep-total" : undefined} data-key={st.key}>
                <td>
                  {KIND_WORDS[st.kind] && <span className="eg-overline ep-chain__kind">{KIND_WORDS[st.kind]}</span>}
                  {st.label}
                </td>
                <td className="num">{st.rate ? fmt(st.rate.value, st.rate.unit) : ""}</td>
                <td className="num">{fmt(st.value.value, st.value.unit)}</td>
                {running && <td className="num">{st.running ? fmt(st.running.value, st.running.unit) : ""}</td>}
                <td className="ep-chain__src"><RefChips refs={compactRefs(st.rate?.source_refs ?? st.value.source_refs)} max={st.rate ? 2 : 1} /></td>
                <td className="num">{l ? fmt(l.theirs, l.ours_unit ?? l.unit) : ""}</td>
                <td className="num">{l?.difference ? fmt(l.difference, l.ours_unit) : ""}</td>
                <td>{l && <span className={`eg-chip ${STATUS_TONE[l.status] ?? ""}`} title={l.note ?? `${l.compare === "rate" ? "rate" : "value"} from p. ${l.page}: “${l.quote}”`}>{STATUS_LABEL[l.status]}</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Lines({ audit, chain, onAct, onRerun }: {
  audit: AuditOut; chain: Chain; onAct: <T>(fn: () => Promise<T>) => Promise<T | null>; onRerun: (r: RerunOut) => void;
}) {
  const [reason, setReason] = useState<Record<string, string>>({});
  if (audit.workings.length === 0) return null;
  const q = `?scenario_id=${chain.scenario_id}`;
  return (
    <section className="eg-card ep-panel">
      <h2 className="eg-card__title">Your workings, line by line</h2>
      {audit.workings.map((w) => (
        <details key={w.id} className="ep-details" open>
          <summary>
            <a href={`/api/workings/${w.id}/file`} target="_blank" rel="noreferrer">{w.filename}</a>
            <span className="eg-muted ep-small"> · {w.lines.length} line{w.lines.length === 1 ? "" : "s"} · {w.uploaded_by}</span>
          </summary>
          <AddLine workingId={w.id} chain={chain} pages={w.pages} onAct={onAct} />
          {w.lines.length > 0 && (
            <table className="ep-table">
              <tbody>
                {w.lines.map((l) => (
                  <tr key={l.id}>
                    <td>
                      <b>{l.label}</b>
                      <div className="ep-small eg-muted">p. {l.page} “{l.quote}”</div>
                      {l.note && <div className="ep-small">{l.note}</div>}
                    </td>
                    <td className="num">{fmt(l.theirs, l.ours_unit ?? l.unit)}</td>
                    <td className="num eg-muted">{l.ours !== null ? `plan ${fmt(l.ours, l.ours_unit)}` : ""}</td>
                    <td><span className={`eg-chip ${STATUS_TONE[l.status] ?? ""}`}>{STATUS_LABEL[l.status]}</span></td>
                    <td className="ep-actions">
                      {l.status === "differs" && l.kind === "yours" && (
                        <button className="eg-btn eg-btn--sm eg-btn--primary" onClick={() => void onAct(async () => {
                          const r = await clientFetch<RerunOut>(`/working-lines/${l.id}/use${q}`, { method: "POST" });
                          onRerun(r);
                          return r;
                        })}>Use my figure</button>
                      )}
                      {l.status === "differs" && l.kind === "regulatory" && l.compare === "rate" && (
                        <span className="ep-row">
                          <span className="eg-input"><input aria-label="Why" placeholder="why (e.g. the order of 2025)" value={reason[l.id] ?? ""} onChange={(e) => setReason({ ...reason, [l.id]: e.target.value })} /></span>
                          <button className="eg-btn eg-btn--sm" disabled={(reason[l.id] ?? "").trim().length < 3} onClick={() => void onAct(() =>
                            clientFetch<Proposal>(`/working-lines/${l.id}/propose`, { method: "POST", body: JSON.stringify({ reason: reason[l.id], scenario_id: chain.scenario_id }) }))}>
                            Send to an analyst
                          </button>
                        </span>
                      )}
                      {(l.status === "differs" || l.status === "unmatched") && (
                        <button className="eg-btn eg-btn--sm eg-btn--ghost" onClick={() => void onAct(() =>
                          clientFetch(`/working-lines/${l.id}/accept-ours`, { method: "POST", body: JSON.stringify({}) }))}>
                          Accept the plan&apos;s figure
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </details>
      ))}
    </section>
  );
}

function AddLine({ workingId, chain, pages, onAct }: {
  workingId: string; chain: Chain; pages: { page: number; name: string }[]; onAct: <T>(fn: () => Promise<T>) => Promise<T | null>;
}) {
  const links = useMemo(() => [
    ...chain.sources.flatMap((s) => [...s.landed, ...s.energy].map((st) => ({ key: st.key, label: `${s.label}: ${st.label}`, rate: !!st.rate }))),
    ...[...chain.energy, ...chain.money].map((st) => ({ key: st.key, label: st.label, rate: false })),
  ], [chain]);
  const [f, setF] = useState({ chain_key: "", compare: "value", label: "", value: "", scale: "units", unit: "INR/kWh", page: String(pages[0]?.page ?? 1), quote: "" });
  const [open, setOpen] = useState(false);
  const link = links.find((x) => x.key === f.chain_key);
  if (!open) return <button className="eg-btn eg-btn--sm eg-btn--ghost" onClick={() => setOpen(true)}>Set a figure against a link by hand</button>;
  return (
    <div className="ep-form ep-addline">
      <label className="eg-field"><span className="eg-field__label">Link</span><span className="eg-input">
        <select value={f.chain_key} onChange={(e) => setF({ ...f, chain_key: e.target.value })}>
          <option value="">(none: the plan has no such link)</option>
          {links.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
        </select></span></label>
      {link?.rate && (
        <label className="eg-field"><span className="eg-field__label">Compare</span><span className="eg-input">
          <select value={f.compare} onChange={(e) => setF({ ...f, compare: e.target.value })}><option value="value">its effect</option><option value="rate">the rule&apos;s rate</option></select></span></label>
      )}
      <label className="eg-field"><span className="eg-field__label">Your label</span><span className="eg-input"><input value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} /></span></label>
      <label className="eg-field"><span className="eg-field__label">Figure as written</span><span className="eg-input"><input inputMode="decimal" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} /></span></label>
      <label className="eg-field"><span className="eg-field__label">In</span><span className="eg-input">
        <select value={f.scale} onChange={(e) => setF({ ...f, scale: e.target.value })}>{["units", "thousand", "lakh", "million", "crore"].map((x) => <option key={x}>{x}</option>)}</select></span></label>
      <label className="eg-field"><span className="eg-field__label">Unit</span><span className="eg-input">
        <select value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })}>{UNITS.map((u) => <option key={u}>{u}</option>)}</select></span></label>
      <label className="eg-field"><span className="eg-field__label">Page or sheet</span><span className="eg-input">
        <select value={f.page} onChange={(e) => setF({ ...f, page: e.target.value })}>{pages.map((p) => <option key={p.page} value={p.page}>{p.name}</option>)}</select></span></label>
      <label className="eg-field ep-addline__quote"><span className="eg-field__label">The words it stands in, copied from that page</span><span className="eg-input"><input value={f.quote} onChange={(e) => setF({ ...f, quote: e.target.value })} /></span></label>
      <div className="ep-row">
        <button className="eg-btn eg-btn--primary eg-btn--sm" disabled={!f.label || !f.value || f.quote.length < 3} onClick={async () => {
          const ok = await onAct(() => clientFetch(`/workings/${workingId}/lines?scenario_id=${chain.scenario_id}`, {
            method: "POST", body: JSON.stringify({ ...f, chain_key: f.chain_key || null, page: Number(f.page), compare: link?.rate ? f.compare : "value" }),
          }));
          if (ok) setOpen(false);
        }}>Compare</button>
        <button className="eg-btn eg-btn--ghost eg-btn--sm" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </div>
  );
}

export function ProposalQueue({ proposals, onAct }: { proposals: Proposal[]; onAct: <T>(fn: () => Promise<T>) => Promise<T | null> }) {
  const [form, setForm] = useState<Record<string, { document_id: string; page: string; quote: string; note: string }>>({});
  const open = proposals.filter((p) => p.status === "open");
  const decided = proposals.filter((p) => p.status !== "open");
  return (
    <section className="eg-card ep-panel">
      <h2 className="eg-card__title">Proposed rule changes</h2>
      <p className="eg-muted ep-small">Accepting makes a new draft of the state&apos;s rulebook with the field changed and cited to the regulation&apos;s page; it reaches plans only after its approval with the golden tests. <a href="/rulebooks">Rulebooks</a></p>
      {open.length === 0 && <p className="eg-muted">None open.</p>}
      {open.map((p) => {
        const f = form[p.id] ?? { document_id: "", page: "", quote: "", note: "" };
        const set = (k: keyof typeof f, v: string) => setForm({ ...form, [p.id]: { ...f, [k]: v } });
        return (
          <article key={p.id} className="ep-proposal">
            <div><b>{p.rule_label ?? p.family}</b> <span className="eg-chip eg-chip--mono">{p.jurisdiction_id} · {p.pointer}</span></div>
            <div className="ep-big">{fmt(p.current, p.unit)} → {fmt(p.proposed, p.unit)}</div>
            <p className="ep-small">{p.reason} <span className="eg-muted">— {p.proposed_by} · <a href={`/plan/audit?c=${p.connection_id}`}>its audit</a></span></p>
            <div className="ep-form">
              <label className="eg-field"><span className="eg-field__label">Regulation (document id)</span><span className="eg-input"><input value={f.document_id} onChange={(e) => set("document_id", e.target.value)} /></span></label>
              <label className="eg-field"><span className="eg-field__label">Page</span><span className="eg-input"><input inputMode="numeric" value={f.page} onChange={(e) => set("page", e.target.value)} /></span></label>
              <label className="eg-field ep-addline__quote"><span className="eg-field__label">Quote printing the new figure</span><span className="eg-input"><input value={f.quote} onChange={(e) => set("quote", e.target.value)} /></span></label>
              <label className="eg-field ep-addline__quote"><span className="eg-field__label">Note</span><span className="eg-input"><input value={f.note} onChange={(e) => set("note", e.target.value)} /></span></label>
            </div>
            <div className="ep-row">
              <button className="eg-btn eg-btn--primary eg-btn--sm" disabled={!f.document_id || !f.page || f.quote.length < 8} onClick={() => void onAct(() =>
                analystFetch(`/rule-proposals/${p.id}/accept`, { method: "POST", body: JSON.stringify({ document_id: f.document_id, page: Number(f.page), quote: f.quote, note: f.note || null }) }))}>
                Draft the rule change
              </button>
              <button className="eg-btn eg-btn--ghost eg-btn--sm" disabled={f.note.trim().length < 3} onClick={() => void onAct(() =>
                analystFetch(`/rule-proposals/${p.id}/reject`, { method: "POST", body: JSON.stringify({ note: f.note }) }))}>
                Keep the rule (give a note)
              </button>
            </div>
          </article>
        );
      })}
      {decided.length > 0 && (
        <table className="ep-table ep-small">
          <tbody>{decided.map((p) => (
            <tr key={p.id}>
              <td>{p.rule_label ?? p.family}</td><td className="num">{fmt(p.current, p.unit)} → {fmt(p.proposed, p.unit)}</td>
              <td>{p.status === "accepted" ? <a href={`/rulebooks/${p.draft_version_id}`}>draft drafted</a> : "rule kept"}</td>
              <td className="eg-muted">{p.decided_by}{p.decision_note ? `: ${p.decision_note}` : ""}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </section>
  );
}

function AuditChat({ connectionId, scenarioId, audit, onChanged, onRerun }: {
  connectionId: string; scenarioId: string; audit: AuditOut; onChanged: () => void; onRerun: (r: RerunOut) => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const logRef = useRef<HTMLOListElement>(null);
  // keep the latest turn in view inside the log (never scroll the page)
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [audit.messages.length, busy]);

  async function send(message: string) {
    if (!message.trim()) return;
    setBusy("Reading against the chain…");
    setError("");
    try {
      const out = await clientFetch<{ reply: string; tool_results: { scenario_id?: string; run_id?: string }[] }>(
        `/connections/${connectionId}/audit/chat`, { method: "POST", body: JSON.stringify({ message, scenario_id: scenarioId }) });
      const rerun = out.tool_results.find((r) => r.run_id && r.scenario_id);
      if (rerun?.run_id && rerun.scenario_id) onRerun({ scenario_id: rerun.scenario_id, scenario: "your figures", run_id: rerun.run_id, status: "queued" });
      setText("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
      onChanged();
    }
  }

  async function upload(file: File) {
    setBusy(`Reading ${file.name}…`);
    setError("");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("scenario_id", scenarioId);
    try {
      await clientFetch(`/connections/${connectionId}/workings`, { method: "POST", body: fd });
      onChanged();
      await send(`I have uploaded my working ${file.name}. Set its figures against the chain and tell me where we differ.`);
    } catch (e) {
      setError((e as Error).message);
      setBusy("");
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <aside className="eg-card ep-panel ep-audit__chat">
      <h2 className="eg-card__title">Check it with your working</h2>
      <p className="eg-muted ep-small">Upload your own working (a spreadsheet, CSV, PDF or text). The assistant sets each figure against the chain; the plan computes every difference. Your own figures become the plan&apos;s inputs; a different charge or loss goes to a jouleWise analyst.</p>
      <ol ref={logRef} className="ep-transcript ep-audit__log" aria-live="polite">
        {audit.messages.map((m) => (
          <li key={m.id} className={`ep-msg ep-msg--${m.role}`}>
            <span className="eg-overline">{m.role === "action" ? "done" : m.role === "user" ? m.actor : "assistant"}</span>
            <span className="ep-msg__text">{m.content}</span>
          </li>
        ))}
        {busy && <li className="ep-msg ep-msg--action"><span className="eg-overline">working</span> {busy}</li>}
      </ol>
      {error && <p className="ep-error">{error}</p>}
      <div className="ep-row">
        <input ref={fileRef} type="file" hidden accept=".xlsx,.xlsm,.csv,.pdf,.txt,.md" onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); }} />
        <button className="eg-btn eg-btn--ghost" disabled={!!busy} onClick={() => fileRef.current?.click()}>Upload a working</button>
      </div>
      <div className="ep-row">
        <span className="eg-input" style={{ flex: 1 }}>
          <textarea aria-label="Message" rows={2} placeholder="e.g. our PPA is ₹3.20; why is the CSS ₹2.11?" value={text}
            onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(text); } }} />
        </span>
        <button className="eg-btn eg-btn--primary" disabled={!!busy || !text.trim()} onClick={() => void send(text)}>Send</button>
      </div>
    </aside>
  );
}
