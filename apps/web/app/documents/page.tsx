import Link from "next/link";
import { apiOrNull, type DocumentOut } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DocumentsPage() {
  const docs = await apiOrNull<DocumentOut[]>("/documents");
  return (
    <>
      <h1 className="eg-h1">
        Regulation <em>library</em>
      </h1>
      <section className="eg-card">
        <div className="eg-card__head">
          <div>
            <h2 className="eg-card__title">
              <span data-icon="file" data-size="20"></span>Source documents
            </h2>
            <p className="eg-card__sub">Every number in ergPLAN links to a page in one of these PDFs.</p>
          </div>
          {docs && <span className="eg-chip">{docs.length} documents</span>}
        </div>
        {docs === null ? (
          <p className="ep-empty">The API is not reachable.</p>
        ) : docs.length === 0 ? (
          <p className="ep-empty">No documents registered yet.</p>
        ) : (
          <table className="ep-table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Regulator</th>
                <th>State</th>
                <th>Order date</th>
                <th className="num">Pages</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td>
                    <Link href={`/documents/${d.id}`}>{d.title}</Link>
                    {d.utilities.length > 0 && <div className="eg-muted" style={{ fontSize: 12 }}>{d.utilities.join(", ")}</div>}
                  </td>
                  <td>{d.regulator ?? "—"}</td>
                  <td>{d.jurisdiction ?? "—"}</td>
                  <td className="nowrap">{d.order_date ?? "—"}</td>
                  <td className="num">{d.pages}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
