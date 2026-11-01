"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ReadingCard } from "@/components/intake/ReadingCard";
import { useCallback, useEffect, useMemo, useState } from "react";
import { clientFetch, monthLabel } from "@/lib/intake";
import { READERS, VERIFICATION, indian, pct, type BillReadOut, type BillReading, type ReadValue } from "@/lib/reading";

// The reading view: the bill on the left, what billx read on the right, each value placed where it
// is printed on the page. "Replay" steps through the stored reading in the order it happened (each
// reader's values, then the agreement between independent readers, then the bill's own checks):
// every step shows billx's stored evidence, nothing is invented (billx 4.2, section 9D.2).

type Step = { key: string; title: string; detail: string; reader?: string };

function allValues(r: BillReading): ReadValue[] {
  const out: ReadValue[] = [...r.fields];
  for (const t of r.tod) for (const c of [t.consumption, t.open_access, t.net]) if (c) out.push(c);
  for (const c of r.charges) out.push(c.amount);
  return out.filter((v) => v.value !== null);
}

function tone(v: ReadValue): string {
  if (v.confirmed || v.verification === "confirmed") return "confirmed";
  return v.verification ?? "unverified";
}

const STATUS: Record<string, string> = {
  passed: "Read and verified",
  confirmed: "Confirmed",
  needs_review: "Some values need your eye",
  unreadable: "Could not be read",
  not_a_bill: "Not an electricity bill",
};

export function BillTheatre({ initial }: { initial: BillReading }) {
  const [r, setR] = useState(initial);
  const [page, setPage] = useState(initial.pages[0] ?? 1);
  const [focus, setFocus] = useState<string | null>(null);
  const [step, setStep] = useState<number>(-1); // -1: everything shown
  const [playing, setPlaying] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [analyst, setAnalyst] = useState(false);
  const [again, setAgain] = useState<BillReadOut | null>(null);
  const router = useRouter();

  useEffect(() => {
    clientFetch<{ role: string; signed_in: boolean }>("/auth/me")
      .then((me) => setAnalyst(me.role === "analyst"))
      .catch(() => setAnalyst(false));
  }, []);

  async function readAgain() {
    setError("");
    try {
      setAgain(await clientFetch<BillReadOut>(`/bills/${r.bill_id}/reread`, { method: "POST" }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const againDone = useCallback((done: BillReadOut) => {
    const same = done.bills.find((b) => b.bill_month && b.bill_month === initial.fields.find((f) => f.path === "period.bill_month")?.value) ?? done.bills[0];
    if (same) router.push(`/plan/intake/bill/${same.id}`);
  }, [router, initial.fields]);

  const values = useMemo(() => allValues(r), [r]);
  const readers = useMemo(() => READERS.filter((x) => r.readers_used.includes(x.id)), [r.readers_used]);
  const steps: Step[] = useMemo(
    () => [
      { key: "pages", title: "The pages", detail: `${r.pages.length} page${r.pages.length === 1 ? "" : "s"} of this bill` },
      ...readers.map((x) => ({ key: `reader:${x.id}`, title: x.name, detail: x.what, reader: x.id })),
      { key: "agree", title: "Agreement", detail: "a value is verified when two independent readers read the same figure" },
      { key: "checks", title: "The bill's own arithmetic", detail: "every total and every quantity × rate recomputed" },
    ],
    [r.pages.length, readers],
  );

  useEffect(() => {
    if (!playing) return;
    if (step >= steps.length - 1) {
      const t = setTimeout(() => { setPlaying(false); setStep(-1); }, 2200);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setStep((s) => s + 1), step < 0 ? 300 : 1900);
    return () => clearTimeout(t);
  }, [playing, step, steps.length]);

  const current = step >= 0 ? steps[step] : null;

  // what the right-hand page shows at this step: each reader's own reading, or the decided value
  const shown = useMemo(() => {
    type Chip = { id: string; path: string; text: string; box: NonNullable<ReadValue["box"]>; tone: string; label: string };
    const chips: Chip[] = [];
    if (current?.key === "pages") return chips;
    for (const v of values) {
      if (current?.reader) {
        const reading = v.readings.find((x) => x.reader === current.reader);
        if (!reading || !reading.printed) continue;
        const box = reading.box ?? v.box;
        const at = reading.box ? reading.page : v.page;
        if (!box || at !== page) continue;
        chips.push({ id: `${v.path}:${current.reader}`, path: v.path, text: reading.printed, box, tone: "reading", label: v.label });
        continue;
      }
      if (!v.box || v.page !== page) continue;
      chips.push({ id: v.path, path: v.path, text: v.value ?? "", box: v.box, tone: tone(v), label: v.label });
    }
    return chips;
  }, [current, values, page]);

  const unplaced = useMemo(() => values.filter((v) => !v.box && v.verification !== "verified"), [values]);
  const review = useMemo(
    () => r.fields.concat(r.tod.flatMap((t) => (t.consumption ? [t.consumption] : [])))
      .filter((v) => v.confirmable && (v.needs_confirmation || (v.verification !== "verified" && !v.confirmed && v.value !== null))),
    [r],
  );

  const focused = values.find((v) => v.path === focus) ?? null;
  const goTo = useCallback((v: ReadValue) => {
    setFocus(v.path);
    if (v.page && v.page !== page) setPage(v.page);
  }, [page]);

  async function confirm(path: string, value: string | null) {
    setBusy(path);
    setError("");
    try {
      await clientFetch(`/bills/${r.bill_id}/confirm`, { method: "POST", body: JSON.stringify({ path, value }) });
      setR(await clientFetch<BillReading>(`/bills/${r.bill_id}/reading`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const src = r.page_url.replace("{page}", String(page));
  const month = r.fields.find((f) => f.path === "period.bill_month")?.value;
  const passedChecks = r.checks.filter((c) => c.status === "pass").length;

  return (
    <div className="ep-theatre">
      <header className="ep-theatre__head">
        <div>
          <div className="eg-overline">Reading view</div>
          <h1 className="eg-h1">{month ? monthLabel(month.length === 7 ? `${month}-01` : month) : r.filename}</h1>
          <p className="eg-muted">
            {r.discom ? r.discom.toUpperCase() : "DISCOM not recognised"} · {r.filename} · pages {r.pages.join(", ")}
            {r.profile_status && r.profile_status !== "final" ? ` · layout ${r.profile_status}` : ""}
          </p>
        </div>
        <div className="ep-row">
          <span className={`eg-chip ${r.accepted ? "eg-chip--accent" : "eg-chip--warning"}`}>
            {r.accepted ? STATUS[r.status] ?? r.status : `${r.outstanding.length || review.length} to check`}
          </span>
          <button className="eg-btn eg-btn--sm" onClick={() => { setStep(-1); setPlaying(true); }} disabled={playing}>
            <span data-icon="play" data-size="14"></span>{playing ? "Replaying…" : "Replay the reading"}
          </button>
          {analyst && !again && (
            <button className="eg-btn eg-btn--sm eg-btn--ghost" onClick={readAgain} title="Read the stored file again with billx's current readers">
              <span data-icon="rotate" data-size="14"></span>Read again
            </button>
          )}
          <a className="ep-cite" href={`/api${r.file_url}`} target="_blank" rel="noreferrer"><span data-icon="file" data-size="14"></span>Open the PDF</a>
        </div>
      </header>
      {again && <ReadingCard initial={again} onDone={againDone} />}

      <ol className="ep-steps" aria-label="How this bill was read">
        {steps.map((s, i) => (
          <li key={s.key} className={i === step ? "is-now" : step > i || step === -1 ? "is-done" : ""}>
            <button onClick={() => { setPlaying(false); setStep(i); }} title={s.detail}>
              <span className="ep-steps__n">{i + 1}</span>{s.title}
            </button>
          </li>
        ))}
        <li className={step === -1 ? "is-now" : ""}>
          <button onClick={() => { setPlaying(false); setStep(-1); }}>
            <span className="ep-steps__n">✓</span>Result
          </button>
        </li>
      </ol>
      <p className="eg-muted ep-steps__detail">
        {current ? current.detail : `${values.filter((v) => v.verification === "verified" || v.confirmed).length} of ${values.length} values verified or confirmed · ${passedChecks} of ${r.checks.length} checks hold`}
      </p>

      {r.pages.length > 1 && (
        <div className="eg-seg ep-pages" role="group" aria-label="Page">
          {r.pages.map((p) => (
            <button key={p} aria-pressed={p === page} onClick={() => setPage(p)}>Page {p}</button>
          ))}
        </div>
      )}

      <div className={`ep-stage${current ? ` ep-stage--${current.key.split(":")[0]}` : ""}`}>
        <figure className="ep-sheet ep-sheet--bill">
          <figcaption>The bill</figcaption>
          <div className="ep-sheet__page">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`/api${src}`} alt={`Page ${page} of the bill`} />
            {values.filter((v) => v.box && v.page === page).map((v) => (
              <span
                key={v.path}
                className={`ep-mark ep-mark--${tone(v)}${focus === v.path ? " is-focus" : ""}`}
                style={{ left: pct(v.box, "x"), top: pct(v.box, "y"), width: pct(v.box, "w"), height: pct(v.box, "h") }}
                onMouseEnter={() => setFocus(v.path)}
                title={`${v.label}: ${v.value ?? ""}`}
              />
            ))}
          </div>
        </figure>

        <figure className="ep-sheet ep-sheet--read" aria-live="polite">
          <figcaption>
            {current?.reader ? `What ${current.title} read` : current?.key === "pages" ? "Waiting for the readers" : "What we read"}
          </figcaption>
          <div className="ep-sheet__page ep-sheet__page--ghost">
            {/* the same page, faint, so every value sits where it is printed */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`/api${src}`} alt="" aria-hidden="true" className="ep-ghost" />
            {shown.map((c, i) => (
              <button
                key={c.id}
                className={`ep-val ep-val--${c.tone}${focus === c.path ? " is-focus" : ""}`}
                style={{ left: pct(c.box, "x"), top: pct(c.box, "y"), minWidth: pct(c.box, "w"), animationDelay: `${Math.min(i * 18, 900)}ms` }}
                onMouseEnter={() => setFocus(c.path)}
                onClick={() => setFocus(c.path)}
                title={c.label}
              >
                {indian(c.text)}
              </button>
            ))}
          </div>
        </figure>
      </div>

      {focused && (
        <section className="eg-card ep-focus">
          <div className="ep-focus__title">
            <b>{focused.label}</b>
            <span className={`eg-chip ep-tone--${tone(focused)}`}>{VERIFICATION[tone(focused)] ?? tone(focused)}</span>
            {focused.page && <span className="eg-muted">page {focused.page}</span>}
          </div>
          <div className="ep-focus__readings">
            {focused.readings.length === 0 && <span className="eg-muted">No reader detail stored for this value.</span>}
            {focused.readings.map((x) => (
              <span key={x.reader} className={`ep-reading${x.value === focused.value ? " is-agree" : ""}`}>
                <small>{x.reader_name}</small>
                <b>{x.printed ?? "—"}</b>
              </span>
            ))}
          </div>
        </section>
      )}

      {r.tod.length > 0 && (
        <section className="eg-card ep-panel">
          <h2 className="eg-card__title">Time-of-day slots</h2>
          <p className="eg-card__sub">As printed on the bill, in {r.tod[0].unit}. Click a figure to see it on the page.</p>
          <table className="ep-table">
            <thead>
              <tr><th>Slot</th><th>Hours</th><th className="num">Consumed</th><th className="num">Open access set off</th><th className="num">Billed by the DISCOM</th><th className="num">Rate</th></tr>
            </thead>
            <tbody>
              {r.tod.map((t) => {
                const rate = r.charges.find((c) => (c.tod_slot ?? c.label).replace(/\s/g, "").toUpperCase().startsWith(t.slot.split(/[\s(]/)[0].replace(/\s/g, "").toUpperCase()) && c.rate);
                return (
                  <tr key={t.slot}>
                    <td>{t.slot}</td>
                    <td className="nowrap">{t.start && t.end ? `${t.start}–${t.end}` : <span className="eg-muted">not printed</span>}</td>
                    {[t.consumption, t.open_access, t.net].map((c, i) => (
                      <td key={i} className="num">
                        {c ? (
                          <button className={`ep-cell ep-tone--${tone(c)}`} onClick={() => goTo(c)}>{indian(c.value)}</button>
                        ) : <span className="eg-muted">—</span>}
                      </td>
                    ))}
                    <td className="num">{rate?.rate ? `₹${rate.rate}` : <span className="eg-muted">—</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      {review.length > 0 && (
        <section className="eg-card ep-panel">
          <h2 className="eg-card__title">Values that need your eye</h2>
          <p className="eg-card__sub">The readers did not agree on these, or only one read them. Pick the right reading or type what the page shows.</p>
          <div className="ep-review">
            {review.map((v) => (
              <div key={v.path} className="ep-review__row">
                <button className="ep-review__label" onClick={() => goTo(v)}>{v.label}{v.page ? <small> · p. {v.page}</small> : null}</button>
                <div className="ep-row">
                  {Array.from(new Map(v.readings.filter((x) => x.printed).map((x) => [x.value ?? x.printed, x])).values()).map((x) => (
                    <button key={x.reader} className="eg-btn eg-btn--sm" disabled={busy !== null} onClick={() => confirm(v.path, x.printed)}>
                      {x.printed} <small className="eg-muted">· {v.readings.filter((y) => (y.value ?? y.printed) === (x.value ?? x.printed)).map((y) => y.reader_name).join(", ")}</small>
                    </button>
                  ))}
                  <span className="eg-input ep-fact__input">
                    <input aria-label={`${v.label}: what the page shows`} placeholder="or type it" value={edits[v.path] ?? ""}
                      onChange={(e) => setEdits({ ...edits, [v.path]: e.target.value })} />
                  </span>
                  <button className="eg-btn eg-btn--sm eg-btn--accent" disabled={busy !== null || !(edits[v.path] ?? "").trim()}
                    onClick={() => confirm(v.path, (edits[v.path] ?? "").trim())}>
                    {busy === v.path ? "Saving…" : "Use this"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {r.checks.length > 0 && (
        <section className="eg-card ep-panel">
          <h2 className="eg-card__title">The bill&apos;s own arithmetic</h2>
          <ul className="ep-checks">
            {r.checks.map((c) => (
              <li key={c.id} className={`ep-check ep-check--${c.status}`}>
                <span className="ep-check__id">{c.id}</span>
                <span>{c.description ?? ""}</span>
                <span className="eg-muted">{c.status === "pass" ? "holds" : c.status === "fail" ? `differs: ${indian(c.actual)} printed, ${indian(c.expected)} computed` : c.status}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {unplaced.length > 0 && (
        <p className="eg-muted ep-note">{unplaced.length} value{unplaced.length > 1 ? "s were" : " was"} read without a position on the page; they are listed above with the slots and checks.</p>
      )}
      {error && <p className="ep-error">{error}</p>}
      <div className="ep-row">
        <Link className="eg-btn eg-btn--ghost" href="/plan/intake">Back to bills</Link>
        <Link className="eg-btn eg-btn--primary" href={`/plan/intake/bill/${r.bill_id}/inputs`}>
          See what planning takes from this bill<span data-icon="arrow-right" data-size="16"></span>
        </Link>
      </div>
    </div>
  );
}
