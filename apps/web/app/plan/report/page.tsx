import Link from "next/link";
import { PlanBuilder } from "@/components/plan/PlanBuilder";
import { apiOrNull } from "@/lib/api";
import type { PlanOut } from "@/lib/plan";

// Journey step 6: the client's own plan, built and shared without an analyst.
export default async function ReportPage({ searchParams }: { searchParams: Promise<{ c?: string }> }) {
  const { c } = await searchParams;
  const plan = c ? await apiOrNull<PlanOut>(`/connections/${c}/plan`) : null;
  if (!c || !plan) {
    return (
      <section className="eg-card ep-panel">
        <h1 className="eg-h1">Your plan</h1>
        <p className="eg-muted">Start with your bill; your plan opens once a site exists.</p>
        <Link className="eg-btn eg-btn--primary" href="/plan/intake">Drop a bill</Link>
      </section>
    );
  }
  return (
    <>
      <div>
        <div className="eg-overline">Step 6 of 6</div>
        <h1 className="eg-h1">Your plan</h1>
        <p className="eg-muted ep-lede">{plan.client} · {plan.site} · {plan.discom.toUpperCase()}. Build it, then share a link that opens without a login, with voice what-if and a PDF.</p>
      </div>
      <PlanBuilder connectionId={c} initial={plan} />
    </>
  );
}
