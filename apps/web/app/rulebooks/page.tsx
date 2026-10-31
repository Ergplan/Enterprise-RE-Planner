import Link from "next/link";
import { apiOrNull } from "@/lib/api";
import { FAMILY_LABEL, type Version } from "@/lib/rulebook";

export const dynamic = "force-dynamic";

const STATUS_TONE: Record<string, string> = {
  approved: "eg-chip--accent",
  draft: "eg-chip--warning",
  rejected: "eg-chip--negative",
  superseded: "",
};

export default async function RulebooksPage() {
  const versions = (await apiOrNull<Version[]>("/rulebooks/versions")) ?? [];
  const byJur = new Map<string, Version[]>();
  for (const v of versions) byJur.set(v.jurisdiction_id, [...(byJur.get(v.jurisdiction_id) ?? []), v]);
  const live = versions.filter((v) => v.status === "approved").length;
  return (
    <>
      <h1 className="eg-h1">
        State <em>rulebooks</em>
      </h1>
      <p className="eg-muted" style={{ margin: 0, maxWidth: 760 }}>
        Tariffs, time-of-day slots, open-access charges and settlement rules as approved data. Engines read approved
        versions only; every row cites its regulation and page.
      </p>
      <div className="ep-row">
        <span className="eg-chip eg-chip--accent">{live} approved</span>
        <span className="eg-chip">{versions.filter((v) => v.status === "draft").length} drafts</span>
      </div>
      {versions.length === 0 && <p className="ep-empty">No rulebooks yet. Read a regulation from the document library.</p>}
      {[...byJur.entries()].map(([jur, vs]) => (
        <section key={jur} className="eg-card">
          <div className="eg-card__head">
            <h2 className="eg-card__title">
              <span data-icon="layers" data-size="20"></span>
              {jur.toUpperCase()}
            </h2>
          </div>
          <table className="ep-table">
            <thead>
              <tr>
                <th>Family</th>
                <th>Version</th>
                <th>Status</th>
                <th>In force from</th>
                <th>Golden tests</th>
                <th className="num">Rows</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {vs.map((v) => (
                <tr key={v.id}>
                  <td>
                    <Link href={`/rulebooks/${v.id}`}>{FAMILY_LABEL[v.family] ?? v.family}</Link>
                  </td>
                  <td>v{v.version}</td>
                  <td>
                    <span className={`eg-chip ${STATUS_TONE[v.status] ?? ""}`}>{v.status}</span>
                  </td>
                  <td className="nowrap">{v.effective_from}</td>
                  <td>{v.golden_status === "green" ? "Passed" : v.golden_status === "red" ? "Failing" : "Not run"}</td>
                  <td className="num">{v.rows}</td>
                  <td className="eg-muted" style={{ fontSize: 12 }}>{v.title}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </>
  );
}
