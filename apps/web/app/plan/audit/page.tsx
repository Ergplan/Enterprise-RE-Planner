import Link from "next/link";
import { AuditScreen } from "@/components/audit/AuditScreen";
import { apiOrNull } from "@/lib/api";
import type { AuditOut, Chain } from "@/lib/audit";
import type { PlanOut } from "@/lib/plan";

// The audit of a plan: the whole chain of charges and losses to the landed cost, the energy settled and
// the saving, each link cited; the client's own working set against it in a chat.
export default async function AuditPage({ searchParams }: { searchParams: Promise<{ c?: string; s?: string }> }) {
  const { c, s } = await searchParams;
  const q = s ? `?scenario_id=${encodeURIComponent(s)}` : "";
  const [chain, audit, plan] = c
    ? await Promise.all([
        apiOrNull<Chain>(`/connections/${c}/chain${q}`),
        apiOrNull<AuditOut>(`/connections/${c}/audit${q}`),
        apiOrNull<PlanOut>(`/connections/${c}/plan`),
      ])
    : [null, null, null];
  if (!c || !chain || !audit) {
    return (
      <section className="eg-card ep-panel">
        <h1 className="eg-h1">Audit the plan</h1>
        <p className="eg-muted">The audit opens once your plan is settled.</p>
        <Link className="eg-btn eg-btn--primary" href={c ? `/results?c=${c}` : "/evaluate"}>Your plan</Link>
      </section>
    );
  }
  const scenarios = (plan?.scenarios ?? []).map((x) => ({ scenario_id: x.scenario_id, name: x.name }));
  return (
    <>
      <div>
        <div className="eg-overline">Audit</div>
        <h1 className="eg-h1">From the generator&apos;s price to your saving</h1>
        <p className="eg-muted ep-lede">
          {plan?.client ? `${plan.client} · ` : ""}{chain.site} · {chain.discom.toUpperCase()}{chain.state ? `, ${chain.state}` : ""}.
          Every charge, loss and settlement step, each with the page of the order or regulation it rests on.{" "}
          <Link href={`/plan/report?c=${c}`}>Back to the plan</Link>
        </p>
      </div>
      <AuditScreen connectionId={c} initialChain={chain} initialAudit={audit} scenarios={scenarios} />
    </>
  );
}
