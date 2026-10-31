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
  const coverage = (await apiOrNull<{ state: string; name: string; families: Record<string, string> }[]>("/rulebooks/coverage")) ?? [];
  const byJur = new Map<string, Version[]>();
  const order = { approved: 0, draft: 1, rejected: 2, superseded: 3 } as Record<string, number>;
  versions.sort((a, b) => a.jurisdiction_id.localeCompare(b.jurisdiction_id) || a.family.localeCompare(b.family) || order[a.status] - order[b.status]);
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
      {coverage.length > 0 && (
        <section className="eg-card ep-panel">
          <div className="eg-overline" style={{ marginBottom: 8 }}>Coverage today</div>
          <table className="ep-table ep-small">
            <thead><tr><th>State</th>{Object.keys(coverage[0].families).map((f) => <th key={f}>{FAMILY_LABEL[f] ?? f}</th>)}</tr></thead>
            <tbody>
              {coverage.map((c) => (
                <tr key={c.state}>
                  <td>{c.name}</td>
                  {Object.entries(c.families).map(([f, st]) => (
                    <td key={f}><span className={`eg-chip ${st === "approved" ? "eg-chip--accent" : ""}`}>{st}</span></td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
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
                <tr key={v.id} style={v.status === "superseded" || v.status === "rejected" ? { opacity: 0.5 } : undefined}>
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
