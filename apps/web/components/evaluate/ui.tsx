"use client";

import { useId, useState, type ReactNode } from "react";

// Form primitives for the Evaluate page: a labelled field with a "?" that opens its help, a required
// mark, an "Advanced" fold, and a numbered section with its state.

export function Field({ label, help, required, children, unit, hint, wide }: {
  label: string; help?: string; required?: boolean; children: ReactNode; unit?: string; hint?: string; wide?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className={`ep-fld${wide ? " ep-fld--wide" : ""}`}>
      <div className="ep-fld__head">
        <label className="eg-field__label" htmlFor={id}>
          {label}
          {required && <span className="ep-req" aria-label="required"> *</span>}
        </label>
        {help && (
          <button type="button" className="ep-help" aria-expanded={open} aria-label={`About ${label}`} onClick={() => setOpen(!open)}>?</button>
        )}
      </div>
      <div className="ep-fld__ctl">
        <span className="eg-input ep-fld__input">{children}</span>
        {unit && <span className="eg-muted ep-fld__unit">{unit}</span>}
      </div>
      {open && help && <p className="ep-fld__help">{help}</p>}
      {hint && !open && <p className="ep-fld__hint eg-muted">{hint}</p>}
    </div>
  );
}

export function Advanced({ children, label = "Advanced inputs" }: { children: ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="ep-adv">
      <button type="button" className="ep-adv__toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span data-icon={open ? "chevron-down" : "chevron-right"} data-size="14"></span>
        {label}
      </button>
      {open && <div className="ep-adv__body">{children}</div>}
    </div>
  );
}

export type SectionState = "done" | "todo" | "optional";

export function Section({ id, n, title, blurb, state, open, onToggle, children, aside }: {
  id: string; n: number; title: string; blurb?: string; state: SectionState; open: boolean; onToggle: () => void; children: ReactNode; aside?: ReactNode;
}) {
  return (
    <section id={`sec-${id}`} className={`eg-card ep-sec ep-sec--${state}${open ? " ep-sec--open" : ""}`}>
      <header className="ep-sec__head" onClick={onToggle} role="button" tabIndex={0} aria-expanded={open}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onToggle(); } }}>
        <span className={`ep-sec__n ep-sec__n--${state}`} aria-hidden>{state === "done" ? "✓" : n}</span>
        <div className="ep-sec__titles">
          <h2 className="ep-sec__title">{title}</h2>
          {blurb && <p className="ep-sec__blurb">{blurb}</p>}
        </div>
        <div className="ep-sec__aside" onClick={(e) => e.stopPropagation()}>{aside}</div>
        <span className={`ep-sec__chev${open ? " ep-sec__chev--open" : ""}`} data-icon="chevron-down" data-size="18" aria-hidden></span>
      </header>
      {open && <div className="ep-sec__body">{children}</div>}
    </section>
  );
}

export function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} className={`ep-toggle${on ? " ep-toggle--on" : ""}`} onClick={() => onChange(!on)}>
      <span className="ep-toggle__knob" />
    </button>
  );
}

export function Note({ kind = "info", children }: { kind?: "info" | "warn" | "ok"; children: ReactNode }) {
  return <p className={`ep-note ep-note--${kind}`}>{children}</p>;
}
