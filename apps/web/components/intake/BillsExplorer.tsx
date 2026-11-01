"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { clientFetch, monthLabel, refHref } from "@/lib/intake";
import { indian, type AccountSeries, type SearchOut, type Sourced } from "@/lib/reading";

const SLOT_TONES = ["var(--aurora-solar)", "var(--accent)", "var(--aurora-wind)", "var(--aurora-grid)", "var(--c-battery)", "var(--c-hydro)"];

function Fig({ v, money }: { v: Sourced | null; money?: boolean }) {
  if (!v) return <span className="eg-muted">—</span>;
  const href = refHref(v.source_refs[0]);
  const text = `${money ? "₹" : ""}${indian(v.value)}`;
  return href ? <a className="ep-figlink" href={href} target="_blank" rel="noreferrer">{text}</a> : <span>{text}</span>;
}

// Search (Haystack keyword ranking over billx's stored readings) and the months of each account.
// Every figure opens the bill page it was read from.
export function BillsExplorer() {
  const [q, setQ] = useState("");
  const [result, setResult] = useState<SearchOut | null>(null);
  const [accounts, setAccounts] = useState<AccountSeries[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    clientFetch<{ accounts: AccountSeries[] }>("/bill-analytics")
      .then((a) => setAccounts(a.accounts))
      .catch((e) => setError((e as Error).message));
  }, []);

  async function run(e?: React.FormEvent) {
    e?.preventDefault();
    if (!q.trim()) return;
    setError("");
    try {
      setResult(await clientFetch<SearchOut>(`/bill-search?q=${encodeURIComponent(q.trim())}`));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <div>
        <div className="eg-overline">Your bills</div>
        <h1 className="eg-h1">Search and compare your bills</h1>
        <p className="eg-muted ep-lede">Find a bill by anything printed on it, a month, a slot, a charge or a check that did not hold, and see each account month by month.</p>
      </div>
      <form className="ep-row ep-search" onSubmit={run}>
        <span className="eg-input ep-search__input">
          <span data-icon="search" data-size="16"></span>
          <input aria-label="Search your bills" placeholder="e.g. TOD-3 March, power factor, FPPA, G09 fails, PVVNL HV-2" value={q} onChange={(e) => setQ(e.target.value)} />
        </span>
        <button className="eg-btn eg-btn--primary" type="submit">Search</button>
      </form>
      {result && (
        <section className="ep-hits">
          <p className="eg-muted">{result.hits.length} of {result.searched} bills match “{result.query}”.</p>
          {result.hits.map((h) => (
            <Link key={h.bill_id} href={h.reading_url} className="eg-card ep-hit">
              <div className="ep-hit__head">
                <b>{h.bill_month ? monthLabel(h.bill_month) : h.filename}</b>
                <span className="eg-muted">{h.discom?.toUpperCase()} · {h.consumer ?? h.filename}</span>
                <span className={`eg-chip ${h.status === "passed" || h.status === "confirmed" ? "eg-chip--accent" : "eg-chip--warning"}`}>{h.status.replace("_", " ")}</span>
              </div>
              <ul>{h.lines.map((ln) => <li key={ln}>{ln}</li>)}</ul>
            </Link>
          ))}
        </section>
      )}

      {accounts?.map((a) => {
        const slots = Array.from(new Set(a.months.flatMap((m) => m.slots.map((s) => s.slot))));
        const peak = Math.max(1, ...a.months.map((m) => m.slots.reduce((t, s) => t + Number(s.consumption?.value ?? 0), 0)));
        return (
          <section key={a.account ?? "none"} className="eg-card ep-panel">
            <h2 className="eg-card__title">{a.consumer ?? "Account"}{a.account ? ` · ${a.account}` : ""}</h2>
            <p className="eg-card__sub">{a.discom?.toUpperCase() ?? ""} · {a.months.length} month{a.months.length === 1 ? "" : "s"}</p>
            {slots.length > 0 && (
              <div className="ep-months" role="img" aria-label="Consumption by time-of-day slot, month by month">
                {a.months.map((m) => (
                  <div key={m.month} className="ep-month">
                    <div className="ep-month__bar">
                      {m.slots.map((s) => (
                        <span key={s.slot} title={`${s.slot}: ${indian(s.consumption?.value)} ${m.unit}`}
                          style={{ height: `${(Number(s.consumption?.value ?? 0) / peak) * 100}%`, background: SLOT_TONES[slots.indexOf(s.slot) % SLOT_TONES.length] }} />
                      ))}
                    </div>
                    <small>{monthLabel(m.month)}</small>
                  </div>
                ))}
                <div className="ep-legend">
                  {slots.map((s, i) => <span key={s}><i style={{ background: SLOT_TONES[i % SLOT_TONES.length] }}></i>{s}</span>)}
                </div>
              </div>
            )}
            <table className="ep-table">
              <thead>
                <tr><th>Month</th><th className="num">Consumed</th><th className="num">Open access</th><th className="num">Share</th><th className="num">Billed</th><th className="num">Max demand</th><th className="num">PF</th><th className="num">Current charges</th><th className="num">Net payable</th></tr>
              </thead>
              <tbody>
                {a.months.map((m) => (
                  <tr key={m.month}>
                    <td><Link href={`/plan/intake/bill/${m.bill_id}`}>{monthLabel(m.month)}</Link>{!m.verified && <span className="eg-chip eg-chip--warning ep-mini">to check</span>}</td>
                    <td className="num"><Fig v={m.consumption} /></td>
                    <td className="num"><Fig v={m.open_access} /></td>
                    <td className="num">{m.open_access_share ? `${m.open_access_share.value}%` : "—"}</td>
                    <td className="num"><Fig v={m.billed} /></td>
                    <td className="num"><Fig v={m.max_kva} />{m.contract_kva ? <small className="eg-muted"> / {indian(m.contract_kva.value)}</small> : null}</td>
                    <td className="num"><Fig v={m.power_factor} /></td>
                    <td className="num"><Fig v={m.current_charges} money /></td>
                    <td className="num"><Fig v={m.net_payable} money /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        );
      })}
      {accounts && accounts.length === 0 && <p className="ep-empty">No bills yet. <Link href="/plan/intake">Drop a bill</Link> to start.</p>}
      {error && <p className="ep-error">{error}</p>}
    </>
  );
}
