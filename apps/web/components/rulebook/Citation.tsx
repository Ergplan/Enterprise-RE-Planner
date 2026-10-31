import Link from "next/link";
import type { SourceRef } from "@/lib/rulebook";

// One citation: the quote, the page, a link that opens the stored PDF at that page and the in-app page view.
export function Citation({ cite, compact = false }: { cite: SourceRef; compact?: boolean }) {
  if (!cite.document_id || !cite.page) {
    return <span className="eg-chip eg-chip--warning">{cite.kind.replaceAll("_", " ")}</span>;
  }
  return (
    <div className="ep-citation">
      {!compact && cite.quote && <blockquote>{cite.quote}</blockquote>}
      <div className="ep-row">
        <Link className="ep-cite" href={`/documents/${cite.document_id}?page=${cite.page}`}>
          <span data-icon="file" data-size="14"></span>Page {cite.page}
          {cite.printed_page && cite.printed_page !== String(cite.page) ? ` (printed ${cite.printed_page})` : ""}
        </Link>
        <a className="ep-cite" href={`/api/documents/${cite.document_id}#page=${cite.page}`} target="_blank" rel="noreferrer">
          Open the PDF at this page
        </a>
        {cite.effective_from && <span className="eg-muted" style={{ fontSize: 12 }}>in force from {cite.effective_from}</span>}
      </div>
    </div>
  );
}
