// The Evaluate page: one draft of everything a consumer tells ergPLAN, in the order they would tell it
// (the factory, the DISCOM and connection, consumption, today's bill and open access, what to evaluate,
// settings), built into a SiteIntake and a mix for the optimizer. Nothing here computes a number.

import type { AssetIn, BillOut, Fact, SiteIntake, SourcedValue } from "./intake";
import type { CandidateSpec, SourceOption } from "./runs";

export type CategoryOut = {
  code: string; label: string; voltage_min_kv: string | null; voltage_max_kv: string | null;
  rate_block: string | null; usual_voltage_kv: string | null;
};
export type DiscomOut = {
  id: string; name: string; state: string; state_name: string; categories: CategoryOut[];
  sourced: Record<string, boolean>; ready: boolean;
};
export type EvaluationOut = {
  connection_id: string; client: string; site: string; state: string | null; discom: string; category: string | null;
  contract_demand_kva: string | null; bills: number; profile_provenance: string | null; created_at: string | null;
  latest_run: { scenario: string | null; scenario_id: string; run_id: string; status: string; saving: { value: string } | null; finished_at: string | null } | null;
};
export type TodayOut = {
  source: string; annual: SourcedValue | null; energy: SourcedValue | null; demand: SourcedValue | null; kwh: SourcedValue | null;
  average_inr_per_kwh: SourcedValue | null; months: number; note: string; gaps: string[];
};

export type TechPick = {
  on: boolean; ownership: string; price: string; max_mw: string; min_mw: string; commissioned: string;
};

export type Draft = {
  connectionId: string | null;
  factory: {
    client_name: string; site_name: string; state: string; industry_shape: string; weekly_off: number[];
    land_acres: string; roof_sqm: string;
  };
  connection: {
    discom: string; category: string; voltage_kv: string; contract_demand_kva: string; consumer_number: string; rate_block: string;
  };
  consumption: {
    mode: "bills" | "annual" | "months";
    annual_kwh: string; year_end: string; max_demand_kva: string; power_factor: string;
    months: { month: string; kwh: string; max_kva: string; bill_inr: string }[];
  };
  today: { open_access: string; assets: AssetIn[] };
  tech: Record<string, TechPick>;
  settings: {
    as_of: string; resolution_min: 15 | 60; standard_plans: boolean;
    analysis_years: string; discount_pct: string; tariff_escalation_pct: string; ppa_escalation_pct: string; om_escalation_pct: string;
  };
};

export const SECTIONS = [
  { id: "factory", n: 1, title: "Your factory", short: "Factory" },
  { id: "connection", n: 2, title: "DISCOM and connection", short: "DISCOM" },
  { id: "consumption", n: 3, title: "Consumption", short: "Consumption" },
  { id: "today", n: 4, title: "Today's bill and open access", short: "Today" },
  { id: "tech", n: 5, title: "What to evaluate", short: "Technologies" },
  { id: "settings", n: 6, title: "Analysis settings", short: "Settings" },
] as const;
export type SectionId = (typeof SECTIONS)[number]["id"];

export const OPEN_ACCESS_CHOICES: [string, string][] = [
  ["none", "None: all my power comes from the DISCOM"],
  ["captive", "Captive open access"],
  ["group_captive", "Group captive"],
  ["third_party", "Third-party open access (a PPA)"],
  ["exchange", "Power exchange purchases"],
  ["geoa", "Green energy open access (GEOA)"],
  ["green_tariff", "Green tariff from the DISCOM"],
  ["open_access", "Open access, kind not known"],
];

export const OWNERSHIP_LABEL: Record<string, string> = {
  captive: "Captive (I own 26%+ and take 51%+)",
  group_captive: "Group captive",
  third_party: "Third party (a PPA)",
};

export const TECH_GROUPS: { id: string; title: string; blurb: string }[] = [
  { id: "At your site", title: "Behind the meter", blurb: "Built inside your premises; no open-access charges, no banking." },
  { id: "Solar", title: "Open-access solar", blurb: "A plant elsewhere in the state (or on the inter-state grid) wheeled to your meter." },
  { id: "Wind", title: "Open-access wind", blurb: "Evening and monsoon energy that solar does not give." },
  { id: "Solar-wind hybrid", title: "Open-access hybrid", blurb: "Solar and wind at one point of connection, a flatter profile." },
  { id: "Power exchange (buy only)", title: "Power exchange", blurb: "Bought block by block at the clearing price. You never sell." },
];

export const DEFAULT_ON = new Set(["rooftop_pv", "oa_solar_intra", "btm_bess"]);

export function emptyDraft(): Draft {
  const today = new Date();
  const prev = new Date(today.getFullYear(), today.getMonth() - 1, 1);
  return {
    connectionId: null,
    factory: { client_name: "", site_name: "", state: "", industry_shape: "two_shift", weekly_off: [6], land_acres: "", roof_sqm: "" },
    connection: { discom: "", category: "", voltage_kv: "", contract_demand_kva: "", consumer_number: "", rate_block: "" },
    consumption: {
      mode: "annual", annual_kwh: "", year_end: `${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, "0")}`,
      max_demand_kva: "", power_factor: "", months: [],
    },
    today: { open_access: "", assets: [] },
    tech: {},
    settings: {
      as_of: today.toISOString().slice(0, 10), resolution_min: 60, standard_plans: false,
      analysis_years: "25", discount_pct: "10", tariff_escalation_pct: "3", ppa_escalation_pct: "0", om_escalation_pct: "4",
    },
  };
}

export function techDefaults(options: SourceOption[], ownership: string | null): Record<string, TechPick> {
  const out: Record<string, TechPick> = {};
  for (const o of options) {
    out[o.kind] = {
      on: o.available && DEFAULT_ON.has(o.kind),
      ownership: o.ownerships.includes(ownership ?? "") ? (ownership as string) : o.ownerships[0] ?? "",
      price: "", max_mw: "", min_mw: "", commissioned: "",
    };
  }
  return out;
}

// The draft from a saved intake (opening an existing evaluation).
export function draftFromIntake(it: SiteIntake, connectionId: string, bills: BillOut[]): Draft {
  const d = emptyDraft();
  d.connectionId = connectionId;
  d.factory = {
    client_name: it.client_name.value, site_name: it.site_name.value, state: it.state.value,
    industry_shape: it.industry_shape.value, weekly_off: it.weekly_off.value,
    land_acres: it.land_acres?.value ?? "", roof_sqm: it.roof_sqm?.value ?? "",
  };
  d.connection = {
    discom: it.discom.value, category: it.category.value, voltage_kv: it.voltage_kv.value,
    contract_demand_kva: it.contract_demand_kva.value, consumer_number: it.consumer_number?.value ?? "",
    rate_block: it.rate_block?.value ?? "",
  };
  const fromBills = it.months.some((m) => m.energy.provenance === "bill") && bills.some((b) => b.accepted);
  const assumedYear = it.months.length === 12 && it.months.every((m) => m.energy.provenance === "assumption");
  d.consumption = {
    mode: fromBills ? "bills" : assumedYear ? "annual" : "months",
    annual_kwh: assumedYear ? String(it.months.reduce((a, m) => a + Number(m.energy.value), 0)) : "",
    year_end: it.months.length ? it.months[it.months.length - 1].month.slice(0, 7) : d.consumption.year_end,
    max_demand_kva: it.months.find((m) => m.max_kva)?.max_kva?.value ?? "",
    power_factor: it.months.find((m) => m.power_factor?.provenance !== "assumption")?.power_factor?.value ?? "",
    months: it.months.map((m) => ({ month: m.month.slice(0, 7), kwh: m.energy.value, max_kva: m.max_kva?.value ?? "", bill_inr: m.bill_inr?.value ?? "" })),
  };
  d.today = { open_access: it.open_access?.value ?? "", assets: it.assets };
  return d;
}

export type Missing = { section: SectionId; what: string };

export function missing(d: Draft, bills: BillOut[]): Missing[] {
  const out: Missing[] = [];
  if (!d.factory.client_name.trim()) out.push({ section: "factory", what: "the company's name" });
  if (!d.factory.site_name.trim()) out.push({ section: "factory", what: "the site's name or town" });
  if (!d.factory.state) out.push({ section: "factory", what: "the state" });
  if (!d.factory.industry_shape) out.push({ section: "factory", what: "how the plant runs" });
  if (!d.connection.discom) out.push({ section: "connection", what: "the DISCOM" });
  if (!d.connection.category) out.push({ section: "connection", what: "the tariff category" });
  if (!(Number(d.connection.voltage_kv) > 0)) out.push({ section: "connection", what: "the supply voltage" });
  if (!(Number(d.connection.contract_demand_kva) > 0)) out.push({ section: "connection", what: "the contract demand" });
  const accepted = bills.filter((b) => b.accepted).length;
  if (d.consumption.mode === "bills") {
    if (accepted === 0) out.push({ section: "consumption", what: "an accepted bill (or type the year's units)" });
  } else if (d.consumption.mode === "annual") {
    if (!(Number(d.consumption.annual_kwh) > 0)) out.push({ section: "consumption", what: "the year's units" });
  } else if (!d.consumption.months.some((m) => Number(m.kwh) > 0)) {
    out.push({ section: "consumption", what: "at least one month's units" });
  }
  if (!Object.values(d.tech).some((t) => t.on)) out.push({ section: "tech", what: "at least one technology to evaluate" });
  return out;
}

export function sectionDone(d: Draft, bills: BillOut[], id: SectionId): boolean {
  if (id === "today") return !!d.today.open_access || d.today.assets.length > 0 || !!d.connectionId;
  if (id === "settings") return true;
  return !missing(d, bills).some((m) => m.section === id);
}

// Overrides for /intake/from-bills: everything the client typed over what the bills say.
export function overridesFromDraft(d: Draft): Record<string, unknown> {
  const o: Record<string, unknown> = {};
  const f = d.factory, c = d.connection;
  if (f.client_name.trim()) o.client_name = f.client_name.trim();
  if (f.site_name.trim()) o.site_name = f.site_name.trim();
  if (f.industry_shape) o.industry_shape = f.industry_shape;
  if (f.weekly_off) o.weekly_off = f.weekly_off;
  if (f.land_acres) o.land_acres = f.land_acres;
  if (f.roof_sqm) o.roof_sqm = f.roof_sqm;
  if (c.discom) o.discom = c.discom;
  if (c.category) o.category = c.category;
  if (c.voltage_kv) o.voltage_kv = c.voltage_kv;
  if (c.contract_demand_kva) o.contract_demand_kva = c.contract_demand_kva;
  if (c.rate_block) o.rate_block = c.rate_block;
  if (d.today.open_access) o.open_access = d.today.open_access;
  if (d.today.assets.length) o.assets = d.today.assets;
  return o;
}

// The body for /intake/typed when there are no bills.
export function typedFromDraft(d: Draft): Record<string, unknown> {
  const f = d.factory, c = d.connection, k = d.consumption;
  const body: Record<string, unknown> = {
    client_name: f.client_name.trim(), site_name: f.site_name.trim(), state: f.state, discom: c.discom, category: c.category,
    voltage_kv: c.voltage_kv, contract_demand_kva: c.contract_demand_kva, industry_shape: f.industry_shape, weekly_off: f.weekly_off,
    assets: d.today.assets,
  };
  if (c.consumer_number) body.consumer_number = c.consumer_number;
  if (c.rate_block) body.rate_block = c.rate_block;
  if (f.land_acres) body.land_acres = f.land_acres;
  if (f.roof_sqm) body.roof_sqm = f.roof_sqm;
  if (d.today.open_access) body.open_access = d.today.open_access;
  if (k.max_demand_kva) body.max_demand_kva = k.max_demand_kva;
  if (k.power_factor) body.power_factor = k.power_factor;
  if (k.mode === "annual") {
    body.annual_kwh = k.annual_kwh;
    if (k.year_end) body.year_end = `${k.year_end}-01`;
  } else {
    body.months = k.months.filter((m) => Number(m.kwh) > 0).map((m) => ({
      month: `${m.month}-01`, kwh: m.kwh, ...(m.max_kva ? { max_kva: m.max_kva } : {}), ...(m.bill_inr ? { bill_inr: m.bill_inr } : {}),
    }));
  }
  return body;
}

export function mixFromDraft(d: Draft, options: SourceOption[]): { sources: CandidateSpec[]; resolution_min: number; as_of: string; finance: Record<string, string | number> } {
  const sources: CandidateSpec[] = [];
  for (const o of options) {
    const t = d.tech[o.kind];
    if (!t?.on) continue;
    const c: CandidateSpec = { kind: o.kind };
    if (o.ownerships.length && t.ownership) c.ownership = t.ownership;
    if (t.price.trim() && o.price_kind === "ppa") c.price_inr_per_kwh = t.price.trim();
    if (t.max_mw.trim()) c.max_mw = t.max_mw.trim();
    if (t.min_mw.trim()) c.min_mw = t.min_mw.trim();
    if (t.commissioned) c.commissioned = t.commissioned;
    sources.push(c);
  }
  const s = d.settings;
  const finance: Record<string, string | number> = {};
  if (s.analysis_years) finance.analysis_years = Number(s.analysis_years);
  for (const k of ["discount_pct", "tariff_escalation_pct", "ppa_escalation_pct", "om_escalation_pct"] as const) if (s[k] !== "") finance[k] = s[k];
  return { sources, resolution_min: s.resolution_min, as_of: s.as_of, finance };
}

export function provenanceOf(f: Fact<unknown> | null | undefined): string {
  return f ? f.provenance : "";
}

const KEY = "ergplan-evaluate-draft";

export function loadDraft(): Draft | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Draft) : null;
  } catch {
    return null;
  }
}

export function saveDraft(d: Draft): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(d));
  } catch {
    /* storage may be unavailable */
  }
}

export function clearDraft(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

// Display only: these format what the API already computed in Decimal. Nothing formatted here goes
// back to the API; request bodies carry the typed strings as the person entered them.
export function inr(v: string | number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  const abs = Math.abs(n);
  if (abs >= 1e7) return `${n < 0 ? "−" : ""}₹${(abs / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 2 })} cr`;
  if (abs >= 1e5) return `${n < 0 ? "−" : ""}₹${(abs / 1e5).toLocaleString("en-IN", { maximumFractionDigits: 1 })} lakh`;
  return `${n < 0 ? "−" : ""}₹${abs.toLocaleString("en-IN", { maximumFractionDigits: digits })}`;
}

export function num(v: string | number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString("en-IN", { maximumFractionDigits: digits }) : String(v);
}
