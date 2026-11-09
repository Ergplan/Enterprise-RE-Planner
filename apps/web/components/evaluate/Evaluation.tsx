"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { VoicePanel } from "@/components/voice/VoicePanel";
import {
  SECTIONS, clearDraft, draftFromIntake, emptyDraft, loadDraft, missing, mixFromDraft, overridesFromDraft, saveDraft,
  sectionDone, techDefaults, typedFromDraft, type DiscomOut, type Draft, type SectionId, type TodayOut,
} from "@/lib/evaluate";
import { clientFetch, type BillOut, type ConnectionOut, type ShapeOut, type SiteIntake } from "@/lib/intake";
import type { PlanInputs } from "@/lib/reading";
import type { SourceOption } from "@/lib/runs";
import { ConnectionSection, ConsumptionSection, FactorySection } from "./SectionsA";
import { SettingsSection, TechSection, TodaySection } from "./SectionsB";
import { Section, type SectionState } from "./ui";

type BuildOut = { connection_id: string; warnings: string[]; load_profile_version: number };
type MixOut = { scenario_id: string; run_id: string | null; status: string };

// The Evaluate page: every input in the order a consumer would give it, one section at a time, with the
// assistant beside it; "Save" builds the site and its load profile; "Get results" sizes the chosen mix.
export function Evaluation({ connectionId }: { connectionId: string | null }) {
  const router = useRouter();
  const [draft, setDraft] = useState<Draft>(() => emptyDraft());
  const [bills, setBills] = useState<BillOut[]>([]);
  const [discoms, setDiscoms] = useState<DiscomOut[]>([]);
  const [shapes, setShapes] = useState<ShapeOut[]>([]);
  const [options, setOptions] = useState<SourceOption[]>([]);
  const [today, setToday] = useState<TodayOut | null>(null);
  const [planInputs, setPlanInputs] = useState<PlanInputs | null>(null);
  const [open, setOpen] = useState<Record<SectionId, boolean>>({ factory: true, connection: true, consumption: true, today: false, tech: true, settings: false });
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState<string>("");
  const [error, setError] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [showAssistant, setShowAssistant] = useState(false);
  const dirty = useRef(false);

  // the assistant sits beside the form on a wide screen; narrower, it is a drawer opened on demand
  useEffect(() => {
    setShowAssistant(window.innerWidth > 1500);
  }, []);

  const set = useCallback((fn: (d: Draft) => Draft) => {
    dirty.current = true;
    setDraft((cur) => fn(cur));
  }, []);

  // reference lists
  useEffect(() => {
    void Promise.all([
      clientFetch<DiscomOut[]>("/intake/discoms").catch(() => [] as DiscomOut[]),
      clientFetch<ShapeOut[]>("/intake/shapes").catch(() => [] as ShapeOut[]),
      clientFetch<SourceOption[]>("/mix/options").catch(() => [] as SourceOption[]),
    ]).then(([d, s, o]) => { setDiscoms(d); setShapes(s); setOptions(o); });
  }, []);

  // the draft: an existing evaluation from the API, else the browser's unsent draft
  useEffect(() => {
    let alive = true;
    (async () => {
      if (connectionId) {
        try {
          const [conn, intake] = await Promise.all([
            clientFetch<ConnectionOut>(`/connections/${connectionId}`),
            clientFetch<SiteIntake>(`/connections/${connectionId}/intake`).catch(() => null),
          ]);
          const got = await Promise.all(conn.bills.map((b) => clientFetch<BillOut>(`/bills/${b.id}`).catch(() => null)));
          const bl = got.filter((b): b is BillOut => b !== null);
          if (!alive) return;
          setBills(bl);
          if (intake) setDraft(draftFromIntake(intake, connectionId, bl));
          else setDraft((d) => ({ ...d, connectionId }));
          void refreshToday(connectionId);
        } catch (e) {
          setError((e as Error).message);
        }
      } else {
        const saved = loadDraft();
        if (saved && !saved.connectionId) setDraft(saved);
      }
      setLoaded(true);
    })();
    return () => { alive = false; };
  }, [connectionId]);

  // technology defaults once the options are known (and once per connection's recorded arrangement)
  useEffect(() => {
    if (!options.length) return;
    setDraft((d) => (Object.keys(d.tech).length ? d : { ...d, tech: techDefaults(options, d.today.open_access || null) }));
  }, [options]);

  // keep the unsent draft in the browser
  useEffect(() => {
    if (loaded && !draft.connectionId) saveDraft(draft);
  }, [draft, loaded]);

  // the recognition from the latest accepted bill prefills the connection
  useEffect(() => {
    const latest = [...bills].filter((b) => b.accepted).sort((a, b) => (a.bill_month ?? "").localeCompare(b.bill_month ?? "")).pop();
    if (!latest) return;
    clientFetch<PlanInputs>(`/bills/${latest.id}/plan-inputs`).then((pi) => {
      setPlanInputs(pi);
      const r = pi.recognition;
      setDraft((d) => {
        const next = { ...d, connection: { ...d.connection }, factory: { ...d.factory }, consumption: { ...d.consumption }, today: { ...d.today } };
        if (r.discom && !d.connection.discom) next.connection.discom = r.discom;
        if (r.state && !d.factory.state) next.factory.state = r.state;
        if (!d.connection.category && (pi.category_code || pi.tariff_category)) next.connection.category = pi.category_code ?? pi.tariff_category ?? "";
        const cd = pi.facts.find((x) => x.key === "demand.contract_kva")?.value.value;
        if (!d.connection.contract_demand_kva && cd) next.connection.contract_demand_kva = String(cd);
        if (!d.today.open_access && r.open_access === "open_access" && r.open_access_kinds.length === 1) next.today.open_access = r.open_access_kinds[0];
        next.consumption.mode = "bills";
        return next;
      });
    }).catch(() => undefined);
  }, [bills]);

  async function refreshToday(cid: string) {
    try {
      setToday(await clientFetch<TodayOut>(`/connections/${cid}/today`));
    } catch {
      setToday(null);
    }
  }

  const onBills = useCallback((got: BillOut[]) => {
    setBills((cur) => [...cur.filter((b) => !got.some((g) => g.id === b.id)), ...got].sort((a, b) => (a.bill_month ?? "").localeCompare(b.bill_month ?? "")));
  }, []);

  const gaps = useMemo(() => missing(draft, bills), [draft, bills]);
  const discom = discoms.find((x) => x.id === draft.connection.discom);
  const canSave = gaps.filter((g) => g.section !== "tech").length === 0 && (!discom || discom.ready);

  async function save(): Promise<string | null> {
    setError("");
    setBusy("Building your site and its load profile…");
    try {
      const accepted = bills.filter((b) => b.accepted).map((b) => b.id);
      let intake: SiteIntake;
      if (draft.consumption.mode === "bills" && accepted.length) {
        intake = await clientFetch<SiteIntake>("/intake/from-bills", { method: "POST", body: JSON.stringify({ bill_ids: accepted, overrides: overridesFromDraft(draft) }) });
      } else {
        intake = await clientFetch<SiteIntake>("/intake/typed", { method: "POST", body: JSON.stringify(typedFromDraft(draft)) });
      }
      const out = await clientFetch<BuildOut>("/sites", { method: "POST", body: JSON.stringify({ intake, connection_id: draft.connectionId ?? undefined }) });
      setWarnings(out.warnings);
      dirty.current = false;
      if (!draft.connectionId) {
        clearDraft();
        setDraft((d) => ({ ...d, connectionId: out.connection_id }));
        window.history.replaceState(null, "", `/evaluate?c=${out.connection_id}`);
      }
      await refreshToday(out.connection_id);
      setOpen((o) => ({ ...o, today: true }));
      return out.connection_id;
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setBusy("");
    }
  }

  async function getResults() {
    const cid = dirty.current || !draft.connectionId ? await save() : draft.connectionId;
    if (!cid) return;
    setError("");
    setBusy("Sizing your mix…");
    try {
      const mix = mixFromDraft(draft, options);
      const out = await clientFetch<MixOut>(`/connections/${cid}/mix`, { method: "POST", body: JSON.stringify(mix) });
      if (draft.settings.standard_plans) {
        await clientFetch(`/connections/${cid}/plan?as_of=${draft.settings.as_of}&resolution_min=${draft.settings.resolution_min}`, { method: "POST" }).catch(() => undefined);
      }
      router.push(`/results?c=${cid}&s=${out.scenario_id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy("");
    }
  }

  // the assistant works on the same facts the form holds
  const assistantState = useMemo(() => {
    const f = (v: unknown) => ({ value: v, provenance: "client_stated" });
    const st: Record<string, unknown> = {};
    const { factory: fa, connection: c, consumption: k } = draft;
    if (fa.client_name) st.client_name = f(fa.client_name);
    if (fa.site_name) st.site_name = f(fa.site_name);
    if (fa.state) st.state = f(fa.state);
    if (c.discom) st.discom = f(c.discom);
    if (c.category) st.category = f(c.category);
    if (c.voltage_kv) st.voltage_kv = f(c.voltage_kv);
    if (c.contract_demand_kva) st.contract_demand_kva = f(c.contract_demand_kva);
    if (c.consumer_number) st.consumer_number = f(c.consumer_number);
    if (fa.industry_shape) st.industry_shape = f(fa.industry_shape);
    st.weekly_off = f(fa.weekly_off);
    if (fa.roof_sqm) st.roof_sqm = f(fa.roof_sqm);
    if (fa.land_acres) st.land_acres = f(fa.land_acres);
    if (k.mode === "months" && k.months.length) st.months = k.months.filter((m) => m.kwh).map((m) => ({ month: `${m.month}-01`, energy: f(m.kwh), ...(m.max_kva ? { max_kva: f(m.max_kva) } : {}) }));
    return st;
  }, [draft]);

  const fromAssistant = useCallback((s: Record<string, unknown>) => {
    const v = (k: string): string => { const x = s[k] as { value?: unknown } | undefined; return x && x.value !== undefined && x.value !== null ? String(x.value) : ""; };
    set((d) => {
      const next: Draft = { ...d, factory: { ...d.factory }, connection: { ...d.connection }, consumption: { ...d.consumption } };
      if (v("client_name")) next.factory.client_name = v("client_name");
      if (v("site_name")) next.factory.site_name = v("site_name");
      if (v("state")) next.factory.state = v("state");
      if (v("industry_shape")) next.factory.industry_shape = v("industry_shape");
      const wo = (s.weekly_off as { value?: number[] } | undefined)?.value;
      if (Array.isArray(wo)) next.factory.weekly_off = wo;
      if (v("roof_sqm")) next.factory.roof_sqm = v("roof_sqm");
      if (v("land_acres")) next.factory.land_acres = v("land_acres");
      if (v("discom")) next.connection.discom = v("discom");
      if (v("category")) next.connection.category = v("category");
      if (v("voltage_kv")) next.connection.voltage_kv = v("voltage_kv");
      if (v("contract_demand_kva")) next.connection.contract_demand_kva = v("contract_demand_kva");
      if (v("consumer_number")) next.connection.consumer_number = v("consumer_number");
      const months = s.months as { month: string; energy: { value: string }; max_kva?: { value: string }; bill_inr?: { value: string } }[] | undefined;
      if (Array.isArray(months) && months.length) {
        next.consumption.mode = "months";
        next.consumption.months = months.map((m) => ({ month: m.month.slice(0, 7), kwh: m.energy.value, max_kva: m.max_kva?.value ?? "", bill_inr: m.bill_inr?.value ?? "" }));
      }
      return next;
    });
  }, [set]);

  const stateOf = (id: SectionId): SectionState => (id === "today" || id === "settings" ? (sectionDone(draft, bills, id) ? "done" : "optional") : sectionDone(draft, bills, id) ? "done" : "todo");
  const toggle = (id: SectionId) => setOpen((o) => ({ ...o, [id]: !o[id] }));
  const jump = (id: SectionId) => { setOpen((o) => ({ ...o, [id]: true })); document.getElementById(`sec-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" }); };

  return (
    <div className={`ep-ev${showAssistant ? "" : " ep-ev--solo"}`}>
      <aside className="ep-ev__rail">
        <ol className="ep-rail">
          {SECTIONS.map((s) => (
            <li key={s.id}>
              <button className={`ep-rail__item ep-rail__item--${stateOf(s.id)}`} onClick={() => jump(s.id)}>
                <span className="ep-rail__n">{stateOf(s.id) === "done" ? "✓" : s.n}</span>
                <span>{s.short}</span>
              </button>
            </li>
          ))}
        </ol>
        <div className="ep-rail__actions">
          <button className="eg-btn eg-btn--ghost eg-btn--block" disabled={!!busy || !canSave} onClick={() => void save()}>{draft.connectionId ? "Save changes" : "Save inputs"}</button>
          <button className="eg-btn eg-btn--primary eg-btn--block" disabled={!!busy || gaps.length > 0 || (discom ? !discom.ready : false)} onClick={() => void getResults()}>Get results</button>
          {gaps.length > 0 && (
            <div className="ep-rail__missing">
              <span className="eg-overline">Still needed</span>
              <ul>{gaps.map((g, i) => <li key={i}><button className="ep-link" onClick={() => jump(g.section)}>{g.what}</button></li>)}</ul>
            </div>
          )}
          {discom && !discom.ready && <p className="ep-error ep-small">{discom.name}&apos;s tariff is not in ergPLAN yet; a plan cannot be computed for it. Pick another DISCOM or ask jouleWise to source it.</p>}
          {draft.connectionId && (
            <p className="ep-small eg-muted">
              <Link href={`/results?c=${draft.connectionId}`}>Results</Link> · <Link href={`/plan/today?c=${draft.connectionId}`}>Today&apos;s bill</Link> · <Link href={`/plan/landed?c=${draft.connectionId}`}>Landed costs</Link>
            </p>
          )}
          <button className={`eg-btn eg-btn--block${showAssistant ? "" : " eg-btn--ghost"}`} onClick={() => setShowAssistant(!showAssistant)}>
            <span data-icon="mic" data-size="16"></span> {showAssistant ? "Hide the assistant" : "Ask ergPLAN"}
          </button>
        </div>
      </aside>

      <div className="ep-ev__main">
        {busy && <p className="ep-note ep-note--info"><span className="eg-dot eg-dot--live"></span> {busy}</p>}
        {error && <p className="ep-error">{error}</p>}
        {warnings.length > 0 && <ul className="ep-note ep-note--warn ep-list">{warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}

        <Section id="factory" n={1} title="Your factory" blurb="Who you are, where the plant is and how it runs." state={stateOf("factory")} open={open.factory} onToggle={() => toggle("factory")}>
          <FactorySection d={draft} set={set} shapes={shapes} discoms={discoms} />
        </Section>
        <Section id="connection" n={2} title="DISCOM and connection" blurb="Drop your bills and ergPLAN reads the DISCOM, category, voltage and demand; or pick them." state={stateOf("connection")} open={open.connection} onToggle={() => toggle("connection")}
          aside={bills.filter((b) => b.accepted).length ? <span className="eg-chip eg-chip--accent">{bills.filter((b) => b.accepted).length} bill{bills.filter((b) => b.accepted).length > 1 ? "s" : ""} accepted</span> : null}>
          <ConnectionSection d={draft} set={set} discoms={discoms} bills={bills} onBills={onBills} planInputs={planInputs} />
        </Section>
        <Section id="consumption" n={3} title="Consumption" blurb="A year of units: from the bills, or typed." state={stateOf("consumption")} open={open.consumption} onToggle={() => toggle("consumption")}>
          <ConsumptionSection d={draft} set={set} bills={bills} />
        </Section>
        <Section id="today" n={4} title="Today's bill and open access" blurb="What a year costs now, the open access you already take, your existing assets." state={stateOf("today")} open={open.today} onToggle={() => toggle("today")}>
          <TodaySection d={draft} set={set} today={today} bills={bills} discom={discom} />
        </Section>
        <Section id="tech" n={5} title="What to evaluate" blurb="Rooftop solar, a battery, open-access solar, wind or hybrid, group captive, the power exchange." state={stateOf("tech")} open={open.tech} onToggle={() => toggle("tech")}
          aside={<span className="eg-chip">{options.filter((o) => draft.tech[o.kind]?.on).length} selected</span>}>
          <TechSection d={draft} set={set} options={options} discom={discom} />
        </Section>
        <Section id="settings" n={6} title="Analysis settings" blurb="25-year horizon, escalations, discount rate, resolution." state={stateOf("settings")} open={open.settings} onToggle={() => toggle("settings")}>
          <SettingsSection d={draft} set={set} />
        </Section>

        <div className="ep-ev__footer">
          <button className="eg-btn eg-btn--primary eg-btn--lg" disabled={!!busy || gaps.length > 0 || (discom ? !discom.ready : false)} onClick={() => void getResults()}>
            Get results
            <span data-icon="arrow-right" data-size="16"></span>
          </button>
          <span className="eg-muted ep-small">The optimizer sizes every ticked source at least cost over the year, re-settles the dispatch under the state&apos;s rules, and projects {draft.settings.analysis_years || "25"} years. About a minute hourly.</span>
        </div>
      </div>

      {showAssistant && (
        <aside className="ep-ev__assistant">
          <div className="eg-card ep-panel ep-assistant">
            <div className="ep-assistant__head">
              <h2 className="eg-card__title">Ask ergPLAN</h2>
              <button type="button" className="eg-btn eg-btn--ghost eg-btn--sm" aria-label="Close the assistant" onClick={() => setShowAssistant(false)}><span data-icon="close" data-size="14"></span></button>
            </div>
            <p className="eg-muted ep-small">Tell it what is on your bill or ask what a field means; it fills the form and asks for what is still missing. Every value it sets shows up on the left, marked &ldquo;you said&rdquo;.</p>
            <VoicePanel mode="intake" compact initialState={assistantState} onState={fromAssistant}
              intro="Type or talk: e.g. “we are a two-shift forging unit in Greater Noida on NPCL, 2,500 kVA at 11 kV, about 9.6 million units a year”." />
          </div>
        </aside>
      )}
    </div>
  );
}
