"use client";

import { useRef, useState } from "react";
import { BillReview } from "@/components/intake/BillReview";
import { IntakeReview } from "@/components/intake/IntakeReview";
import { TypeFacts } from "@/components/intake/TypeFacts";
import { VoicePanel } from "@/components/voice/VoicePanel";
import { clientFetch, type BillOut, type SiteIntake } from "@/lib/intake";

type Door = "bill" | "tell" | "type";

// Journey step 1: drop a bill, tell us about the site (voice, Stage 7), or type the facts.
export default function IntakePage() {
  const [door, setDoor] = useState<Door>("bill");
  const [bills, setBills] = useState<BillOut[]>([]);
  const [uploading, setUploading] = useState(0);
  const [error, setError] = useState("");
  const [intake, setIntake] = useState<SiteIntake | null>(null);
  const [drag, setDrag] = useState(false);
  const [spoken, setSpoken] = useState<Record<string, unknown> | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function upload(files: FileList | File[]) {
    setError("");
    const list = Array.from(files).filter((f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
    if (list.length === 0) {
      setError("Drop your bills as PDF files.");
      return;
    }
    setUploading((n) => n + list.length);
    await Promise.all(list.map(async (f) => {
      const fd = new FormData();
      fd.append("file", f);
      try {
        const got = await clientFetch<BillOut[]>("/bills", { method: "POST", body: fd });
        setBills((cur) => [...cur.filter((b) => !got.some((g) => g.id === b.id)), ...got]
          .sort((a, b) => (a.bill_month ?? "").localeCompare(b.bill_month ?? "")));
      } catch (e) {
        setError(`${f.name}: ${(e as Error).message}`);
      } finally {
        setUploading((n) => n - 1);
      }
    }));
  }

  async function next() {
    setError("");
    try {
      setIntake(await clientFetch<SiteIntake>("/intake/from-bills", {
        method: "POST",
        body: JSON.stringify({ bill_ids: bills.filter((b) => b.accepted).map((b) => b.id) }),
      }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const ready = bills.filter((b) => b.accepted);
  const pending = bills.filter((b) => !b.accepted);
  return (
    <>
      <div>
        <div className="eg-overline">Step 1 of 6</div>
        <h1 className="eg-h1">Start with your bill</h1>
        <p className="eg-muted ep-lede">
          We read your electricity bills to learn your tariff, demand and monthly energy. Every value we take from a bill links back to its
          page; anything we have to assume is marked so you can correct it.
        </p>
      </div>
      <div className="eg-seg" role="group" aria-label="How to start">
        <button aria-pressed={door === "bill"} onClick={() => setDoor("bill")}><span data-icon="file" data-size="16"></span>Drop a bill</button>
        <button aria-pressed={door === "tell"} onClick={() => setDoor("tell")}><span data-icon="mic" data-size="16"></span>Tell me about your site</button>
        <button aria-pressed={door === "type"} onClick={() => setDoor("type")}><span data-icon="keyboard" data-size="16"></span>Type the facts</button>
      </div>

      {intake ? (
        <>
          <div className="ep-row"><button className="eg-btn eg-btn--ghost eg-btn--sm" onClick={() => setIntake(null)}>Back</button></div>
          <IntakeReview initial={intake} />
        </>
      ) : door === "bill" ? (
        <>
          <section
            className={`eg-glass ep-drop${drag ? " ep-drop--over" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files); }}
          >
            <span data-icon="receipt" data-size="28"></span>
            <h2 className="eg-card__title">Drop up to twelve monthly bills</h2>
            <p className="eg-card__sub">PDF, as your DISCOM sends it. Reading takes a minute or two per bill.</p>
            <input ref={input} type="file" accept="application/pdf" multiple hidden onChange={(e) => e.target.files && upload(e.target.files)} />
            <button className="eg-btn eg-btn--primary" onClick={() => input.current?.click()}>Choose files</button>
            {uploading > 0 && <p className="eg-muted"><span className="eg-dot eg-dot--live"></span> Reading {uploading} bill{uploading > 1 ? "s" : ""}…</p>}
          </section>
          {pending.length > 0 && (
            <p className="eg-muted">
              {pending.length} bill{pending.length > 1 ? "s need" : " needs"} a quick check: confirm the highlighted values (or correct them) and the bill can be used.
            </p>
          )}
          <div className="ep-bills">
            {bills.map((b) => <BillReview key={b.id} bill={b} onChange={(nb) => setBills((cur) => cur.map((x) => (x.id === nb.id ? nb : x)))} />)}
          </div>
          {ready.length > 0 && (
            <div className="ep-row">
              <button className="eg-btn eg-btn--primary" onClick={next}>
                Continue with {ready.length} bill{ready.length > 1 ? "s" : ""}
              </button>
            </div>
          )}
        </>
      ) : door === "tell" ? (
        <section className="eg-card ep-panel">
          <h2 className="eg-card__title">Talk it through</h2>
          <p className="eg-card__sub">
            Say what is on your bill and how the plant runs; each value is set in the same form as typing. When it is complete, review it below.
          </p>
          <VoicePanel mode="intake" onState={setSpoken} intro="Tell me your company, the DISCOM, your contract demand and a month's units from a bill." />
          {spoken && isComplete(spoken) && (
            <button className="eg-btn eg-btn--primary" onClick={() => setIntake(spoken as unknown as SiteIntake)}>Review these facts</button>
          )}
        </section>
      ) : (
        <TypeFacts onReady={setIntake} />
      )}
      {error && <p className="ep-error">{error}</p>}
    </>
  );
}

const REQUIRED = ["client_name", "site_name", "state", "discom", "category", "voltage_kv", "contract_demand_kva", "industry_shape", "weekly_off"];

function isComplete(s: Record<string, unknown>): boolean {
  return REQUIRED.every((k) => k in s) && Array.isArray(s.months) && s.months.length > 0;
}
