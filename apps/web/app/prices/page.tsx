import { PriceUpload } from "@/components/prices/PriceUpload";
import { apiOrNull } from "@/lib/api";

type Vintage = { id: string; segment: string; filename: string; file_sha256: string; rows: number; duplicates_dropped: number;
  date_from: string; date_to: string; source_note: string | null; uploaded_by: string; uploaded_at: string | null; superseded_by: string | null };
type Day = { segment: string; day: string; blocks: number; vintage_id: string };

function months(days: Day[]): string[] {
  return [...new Set(days.map((d) => d.day.slice(0, 7)))].sort();
}

// Analyst: IEX price vintages and a coverage calendar per segment (a cell per day; full = 96 blocks).
export default async function PricesPage() {
  const [vintages, coverage] = await Promise.all([apiOrNull<Vintage[]>("/prices/vintages"), apiOrNull<Day[]>("/prices/coverage")]);
  const bySeg = new Map<string, Day[]>();
  for (const d of coverage ?? []) bySeg.set(d.segment, [...(bySeg.get(d.segment) ?? []), d]);
  return (
    <>
      <div>
        <div className="eg-overline">jouleWise</div>
        <h1 className="eg-h1">Market prices</h1>
        <p className="eg-muted ep-lede">IEX 15-minute clearing prices by segment. Every run pins the vintage it used, so a replaced file never changes a past plan.</p>
      </div>
      <PriceUpload />
      <section className="eg-card ep-panel">
        <div className="eg-overline" style={{ marginBottom: 12 }}>Vintages</div>
        {!vintages?.length ? <p className="ep-empty">No prices loaded yet.</p> : (
          <table className="ep-table">
            <thead><tr><th>Segment</th><th>File</th><th>From</th><th>To</th><th className="num">Blocks</th><th className="num">Duplicates</th><th>Loaded by</th><th>State</th></tr></thead>
            <tbody>
              {vintages.map((v) => (
                <tr key={v.id}>
                  <td><span className="eg-chip eg-chip--mono">{v.segment.toUpperCase()}</span></td>
                  <td title={`sha256 ${v.file_sha256}`}>{v.filename}{v.source_note && <div className="eg-muted" style={{ fontSize: 12 }}>{v.source_note}</div>}</td>
                  <td className="nowrap">{v.date_from}</td><td className="nowrap">{v.date_to}</td>
                  <td className="num">{v.rows.toLocaleString("en-IN")}</td><td className="num">{v.duplicates_dropped}</td>
                  <td>{v.uploaded_by}</td>
                  <td>{v.superseded_by ? <span className="eg-chip">superseded</span> : <span className="eg-chip eg-chip--accent">live</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {[...bySeg.entries()].map(([seg, days]) => {
        const byDay = new Map(days.map((d) => [d.day, d.blocks]));
        return (
          <section key={seg} className="eg-card ep-panel">
            <div className="eg-overline" style={{ marginBottom: 12 }}>{seg.toUpperCase()} coverage</div>
            <div className="ep-cal">
              {months(days).map((m) => {
                const [y, mo] = m.split("-").map(Number);
                const n = new Date(Date.UTC(y, mo, 0)).getUTCDate();
                return (
                  <div key={m} className="ep-cal__row">
                    <span className="eg-muted">{m}</span>
                    {Array.from({ length: 31 }, (_, i) => {
                      const day = `${m}-${String(i + 1).padStart(2, "0")}`;
                      const b = byDay.get(day);
                      return i < n ? <span key={i} className="ep-cal__cell" data-full={b === undefined ? undefined : b >= 96 ? "1" : "0"} title={`${day}: ${b ?? 0} of 96 blocks`} /> : <span key={i} />;
                    })}
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
    </>
  );
}
