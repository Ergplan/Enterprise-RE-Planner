"use client";

import { PROVENANCE_LABEL, refHref, type Fact, type Ref } from "@/lib/intake";

// Where an input came from: a bill value links to the bill page; a statement or an assumption is an
// editable chip (invariant 1: never shown as a sourced fact).
export function ProvenanceChip({ provenance, refx }: { provenance: string; refx?: Ref | null }) {
  const href = refHref(refx);
  const tone = provenance === "assumption" ? "eg-chip--warning" : provenance === "bill" ? "eg-chip--accent" : "";
  const label = PROVENANCE_LABEL[provenance] ?? provenance;
  const title = refx?.note ?? undefined;
  if (href) {
    return (
      <a className={`eg-chip ${tone}`} href={href} target="_blank" rel="noreferrer" title={title} style={{ textDecoration: "none" }}>
        <span data-icon="file" data-size="12"></span>
        {label}
        {refx?.page ? ` · p. ${refx.page}` : ""}
      </a>
    );
  }
  return (
    <span className={`eg-chip ${tone}`} title={title}>
      {label}
    </span>
  );
}

// A labelled value with its provenance; when `onEdit` is given the value can be changed, which makes it client_stated.
export function FactRow<T>({ label, fact, unit, onEdit, render }: {
  label: string;
  fact: Fact<T> | null | undefined;
  unit?: string;
  onEdit?: (v: string) => void;
  render?: (v: T) => string;
}) {
  const shown = fact ? (render ? render(fact.value) : String(fact.value ?? "")) : "";
  return (
    <div className="ep-fact">
      <div className="ep-fact__label">{label}</div>
      <div className="ep-fact__value">
        {onEdit ? (
          <span className="eg-input ep-fact__input">
            <input aria-label={label} defaultValue={shown} onBlur={(e) => e.target.value !== shown && onEdit(e.target.value)} />
          </span>
        ) : (
          <b>{shown || "—"}</b>
        )}
        {unit && <span className="eg-muted"> {unit}</span>}
      </div>
      <div>{fact ? <ProvenanceChip provenance={fact.provenance} refx={fact.ref} /> : <span className="eg-chip">not given</span>}</div>
      {fact?.provenance === "assumption" && fact.ref?.note && <div className="ep-fact__note eg-muted">{fact.ref.note}</div>}
    </div>
  );
}
