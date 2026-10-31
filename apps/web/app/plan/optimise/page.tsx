import Link from "next/link";
import { ScenarioBoard } from "@/components/optimise/ScenarioBoard";
import { apiOrNull } from "@/lib/api";
import type { ConnectionOut } from "@/lib/intake";
import type { ScenarioOut } from "@/lib/runs";

// Journey step 5: sized scenarios compared, each re-settled by the settlement simulator before it is shown.
export default async function OptimisePage({ searchParams }: { searchParams: Promise<{ c?: string; as_of?: string }> }) {
  const { c, as_of } = await searchParams;
  if (!c) {
    return (
      <section className="eg-card ep-panel">
        <h1 className="eg-h1">Optimise</h1>
        <p className="eg-muted">Start with your bill; this step opens once a site exists.</p>
        <Link className="eg-btn eg-btn--primary" href="/plan/intake">Drop a bill</Link>
      </section>
    );
  }
  const conn = await apiOrNull<ConnectionOut>(`/connections/${c}`);
  if (!conn) return <p className="ep-empty">This site was not found.</p>;
  const scenarios = (await apiOrNull<ScenarioOut[]>(`/sites/${conn.site.id}/scenarios`)) ?? [];
  const asOf = as_of ?? new Date().toISOString().slice(0, 10);
  return (
    <>
      <div>
        <div className="eg-overline">Step 5 of 6</div>
        <h1 className="eg-h1">Optimise</h1>
        <p className="eg-muted ep-lede">
          Sizes that cost {conn.client.name} least over a year of 15-minute blocks at {conn.discom_id.toUpperCase()} ({conn.tariff_category}), with every open-access charge, the banking rules and your demand charges.
          Every result is settled again by the regulator&apos;s rules before you see it; the numbers below are the settled ones.
        </p>
      </div>
      <ScenarioBoard siteId={conn.site.id} connectionId={conn.id} initial={scenarios} asOf={asOf} />
    </>
  );
}
