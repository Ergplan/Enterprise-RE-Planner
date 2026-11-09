import type { Ref } from "@/lib/intake";

const LABEL: Record<string, string> = { bill: "bill", client_stated: "you said", assumption: "assumed", measured: "meter", derived: "derived" };

// Citations for a number: a regulation or order page opens the stored PDF at that page (invariant 1);
// a bill value opens the client's bill; statements and assumptions are plain chips.
export function RefChips({ refs, max = 4, kinds = 2 }: { refs: Ref[]; max?: number; kinds?: number }) {
  const docs = refs.filter((r) => (r.kind === "order" || r.kind === "regulation") && r.document_id && r.page);
  const bills = refs.filter((r) => r.kind === "bill");
  const others = refs.filter((r) => !docs.includes(r) && !bills.includes(r));
  const billPages = [...new Set(bills.map((r) => r.bill_id))];
  return (
    <span className="ep-refs">
      {docs.slice(0, max).map((r, i) => (
        <a key={`d${i}`} className="eg-chip eg-chip--accent ep-ref" href={`/api/documents/${r.document_id}#page=${r.page}`}
          target="_blank" rel="noreferrer" title={r.quote ?? undefined}>
          <span data-icon="file" data-size="12"></span>p. {r.page}
        </a>
      ))}
      {docs.length > max && <span className="eg-chip">+{docs.length - max}</span>}
      {billPages.slice(0, 1).map((id) => (
        <a key={`b${id}`} className="eg-chip ep-ref" href={`/api/bills/${id}/file`} target="_blank" rel="noreferrer"
          title={bills.map((b) => b.field_path).filter(Boolean).slice(0, 6).join(", ")}>bill</a>
      ))}
      {others.slice(0, kinds).map((r, i) => (
        <span key={`o${i}`} className={`eg-chip ${r.kind === "assumption" ? "eg-chip--warning" : ""}`} title={r.note ?? undefined}>
          {LABEL[r.kind] ?? r.kind}
        </span>
      ))}
    </span>
  );
}
