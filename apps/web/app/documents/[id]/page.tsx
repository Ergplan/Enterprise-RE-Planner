import Link from "next/link";
import { notFound } from "next/navigation";
import { ReadPanel } from "@/components/rulebook/ReadPanel";
import { apiOrNull, type DocumentOut } from "@/lib/api";
import { pdfPageUrl } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function DocumentPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const { id } = await params;
  const { page } = await searchParams;
  const [doc, jurs] = await Promise.all([
    apiOrNull<DocumentOut>(`/documents/${id}/meta`),
    apiOrNull<{ id: string; state_code: string | null; kind: string }[]>("/rulebooks/jurisdictions"),
  ]);
  if (!doc) notFound();
  const p = Math.min(Math.max(Number(page) || 1, 1), doc.pages);
  const hints = Object.entries(doc.page_hints ?? {});
  const own = new Set(doc.utilities.map((u) => u.toLowerCase()));
  const jurIds = (jurs ?? [])
    .filter((j) => j.state_code === doc.jurisdiction && j.kind !== "regulator")
    .map((j) => j.id)
    .sort((a, b) => Number(own.has(b)) - Number(own.has(a)) || (own.size > 1 ? Number(b === "uppcl") - Number(a === "uppcl") : 0));
  return (
    <>
      <div className="eg-crumbs">
        <Link href="/documents" className="eg-muted">Documents</Link>
        <span data-icon="chevron-right" data-size="14"></span> <b>{doc.title}</b>
      </div>
      <div className="ep-viewer">
        <div style={{ display: "grid", gap: "var(--space-6)" }}>
        <section className="eg-card">
          <dl className="ep-kv">
            <dt>Regulator</dt>
            <dd>{doc.regulator ?? "—"}</dd>
            <dt>State</dt>
            <dd>{doc.jurisdiction ?? "—"}</dd>
            <dt>Order date</dt>
            <dd>{doc.order_date ?? "—"}</dd>
            <dt>Pages</dt>
            <dd>{doc.pages}</dd>
            <dt>SHA-256</dt>
            <dd className="eg-mono">{doc.file_sha256.slice(0, 16)}…</dd>
          </dl>
          {doc.url_public && (
            <p style={{ marginTop: 16 }}>
              <a className="ep-cite" href={doc.url_public} target="_blank" rel="noreferrer">
                <span data-icon="download" data-size="14"></span>Regulator&apos;s copy
              </a>
            </p>
          )}
          {hints.length > 0 && (
            <>
              <div className="eg-overline" style={{ marginTop: 20, marginBottom: 8 }}>Sections</div>
              {hints.map(([name, range]) => (
                <div key={name}>
                  <Link className="ep-cite" href={`/documents/${doc.id}?page=${range[0]}`}>
                    {name.replaceAll("_", " ")} · pages {range[0]}–{range[range.length - 1]}
                  </Link>
                </div>
              ))}
            </>
          )}
          {doc.notes.length > 0 && (
            <>
              <div className="eg-overline" style={{ marginTop: 20, marginBottom: 8 }}>Notes</div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "var(--ink-muted)" }}>
                {doc.notes.map((n) => <li key={n}>{n}</li>)}
              </ul>
            </>
          )}
        </section>
        <ReadPanel documentId={doc.id} defaultPages={String(p)} jurisdictions={jurIds} />
        </div>
        <section className="eg-card ep-page">
          <div className="ep-page__bar">
            <Link className="eg-btn eg-btn--ghost eg-btn--sm" href={`/documents/${doc.id}?page=${Math.max(p - 1, 1)}`} aria-disabled={p <= 1}>
              Previous page
            </Link>
            <span className="eg-chip">Page {p} of {doc.pages}</span>
            <Link className="eg-btn eg-btn--ghost eg-btn--sm" href={`/documents/${doc.id}?page=${Math.min(p + 1, doc.pages)}`} aria-disabled={p >= doc.pages}>
              Next page
            </Link>
            <a className="ep-cite" style={{ marginLeft: "auto" }} href={pdfPageUrl(doc.id, p)} target="_blank" rel="noreferrer">
              <span data-icon="file" data-size="14"></span>Open the PDF at this page
            </a>
          </div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="ep-page__img" src={`/api/documents/${doc.id}/pages/${p}.png`} alt={`${doc.title}, page ${p}`} />
        </section>
      </div>
    </>
  );
}
