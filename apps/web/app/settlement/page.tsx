import Link from "next/link";
import { SettlementExplorer } from "@/components/cost/SettlementExplorer";
import { apiOrNull } from "@/lib/api";
import type { ConnectionOut } from "@/lib/intake";

// Analyst: the settlement explorer for one connection.
export default async function SettlementPage({ searchParams }: { searchParams: Promise<{ c?: string }> }) {
  const { c } = await searchParams;
  const conn = c ? await apiOrNull<ConnectionOut>(`/connections/${c}`) : null;
  return (
    <>
      <div>
        <div className="eg-overline">jouleWise</div>
        <h1 className="eg-h1">Settlement explorer</h1>
        <p className="eg-muted ep-lede">
          {conn ? `${conn.client.name} · ${conn.discom_id.toUpperCase()} · ${conn.tariff_category}. ` : ""}
          Settles open-access sources against the site&apos;s 15-minute load under the approved banking and set-off rules. Set your analyst email on any rulebook page first.
        </p>
      </div>
      {conn ? <SettlementExplorer connectionId={conn.id} /> : <p className="eg-muted">Open a site first: <Link href="/evaluate">start an evaluation</Link>, then use the link from its landed-cost page.</p>}
    </>
  );
}
