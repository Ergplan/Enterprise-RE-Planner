import Link from "next/link";
import { Heatmap } from "@/components/cost/Heatmap";
import { ReplayCard } from "@/components/cost/ReplayCard";
import { apiOrNull } from "@/lib/api";
import type { AvoidedOut, ReplayOut } from "@/lib/cost";
import type { ConnectionOut } from "@/lib/intake";

// Journey step 2: today's cost. Each bill rebuilt from the approved tariff beside the real one; the
// 15-minute avoided cost of grid energy. Every rebuilt number links to its order page.
export default async function TodayPage({ searchParams }: { searchParams: Promise<{ c?: string }> }) {
  const { c } = await searchParams;
  if (!c) {
    return (
      <section className="eg-card ep-panel">
        <h1 className="eg-h1">Today&apos;s cost</h1>
        <p className="eg-muted">Start with your bill; this step opens once a site exists.</p>
        <Link className="eg-btn eg-btn--primary" href="/evaluate">New evaluation</Link>
      </section>
    );
  }
  const [conn, replays, avoided] = await Promise.all([
    apiOrNull<ConnectionOut>(`/connections/${c}`),
    apiOrNull<ReplayOut[]>(`/connections/${c}/replay`),
    apiOrNull<AvoidedOut>(`/connections/${c}/avoided-cost`),
  ]);
  if (!conn) return <p className="ep-empty">This site was not found.</p>;
  return (
    <>
      <div>
        <div className="eg-overline">Detail</div>
        <h1 className="eg-h1">Today&apos;s cost</h1>
        <p className="eg-muted ep-lede">
          {conn.client.name} · {conn.discom_id.toUpperCase()} · {conn.tariff_category} · {Number(conn.voltage_kv)} kV. We rebuild each bill from the
          approved tariff order, line by line; click a page chip to open the order at that page.
        </p>
        <div className="ep-row" style={{ marginTop: "var(--space-3)" }}>
          <Link className="eg-btn eg-btn--primary eg-btn--sm" href={`/plan/landed?c=${c}`}>Landed costs of every source</Link>
          <Link className="eg-btn eg-btn--ghost eg-btn--sm" href={`/evaluate?c=${c}`}>Your inputs</Link>
        </div>
      </div>
      {(replays ?? []).length === 0 && <p className="eg-muted">No accepted bills on this connection yet.</p>}
      {(replays ?? []).map((r) => <ReplayCard key={r.bill_id} r={r} />)}
      {avoided && <Heatmap a={avoided} />}
    </>
  );
}
