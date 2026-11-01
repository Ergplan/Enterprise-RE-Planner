"use client";

import { useEffect, useState } from "react";
import { clientFetch } from "@/lib/intake";
import type { BillReadOut } from "@/lib/reading";

// A file while billx reads it: its pages (drawn by ergPLAN, read by billx only), the honest state
// from billx's job (queued, reading, done, failed) and the time so far. No invented progress.
export function ReadingCard({ initial, onDone }: { initial: BillReadOut; onDone: (r: BillReadOut) => void }) {
  const [r, setR] = useState(initial);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (r.status === "done" || r.status === "failed") return;
    const tick = setInterval(() => setNow(Date.now()), 1000);
    const poll = setInterval(async () => {
      try {
        const next = await clientFetch<BillReadOut>(`/bill-reads/${r.id}`);
        setR(next);
        if (next.status === "done") onDone(next);
      } catch {
        /* the next poll tries again */
      }
    }, 4000);
    return () => { clearInterval(tick); clearInterval(poll); };
  }, [r.id, r.status, onDone]);

  const since = new Date(r.started_at ?? r.created_at).getTime();
  const secs = Math.max(0, Math.round((now - since) / 1000));
  const pages = Array.from({ length: Math.min(r.pages, 8) }, (_, i) => i + 1);
  const state = r.status === "queued" ? "Waiting for the reader" : r.status === "reading" ? "Reading" : r.status === "done" ? "Read" : "Could not be read";
  return (
    <article className={`eg-card ep-readcard ep-readcard--${r.status}`}>
      <div className="ep-readcard__pages" aria-hidden="true">
        {pages.map((p) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img key={p} src={`/api${r.page_url.replace("{page}", String(p))}`} alt="" loading="lazy" />
        ))}
      </div>
      <div className="ep-readcard__text">
        <h3 className="eg-card__title">{r.filename ?? "Bill"}</h3>
        <p className="eg-card__sub">
          {r.pages} page{r.pages === 1 ? "" : "s"} · {state}
          {r.status === "reading" || r.status === "queued" ? ` · ${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}` : ""}
        </p>
        {(r.status === "reading" || r.status === "queued") && (
          <p className="eg-muted ep-note">
            <span className="eg-dot eg-dot--live"></span> billx reads every page with local OCR, Docling&apos;s tables and two model readers,
            and checks the bill&apos;s own arithmetic. A scanned bill takes a few minutes.
          </p>
        )}
        {r.status === "failed" && <p className="ep-error">{r.error ?? "The reader could not read this file."}</p>}
      </div>
    </article>
  );
}
