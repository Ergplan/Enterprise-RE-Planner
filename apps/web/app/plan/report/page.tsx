import Link from "next/link";
import { PlanBuilder } from "@/components/plan/PlanBuilder";
import { apiOrNull } from "@/lib/api";
import type { PlanOut } from "@/lib/plan";

// Share and audit: the client's plan as the shared page will show it, with the link and the PDF.
export default async function ReportPage({ searchParams }: { searchParams: Promise<{ c?: string }> }) {
  const { c } = await searchParams;
  const plan = c ? await apiOrNull<PlanOut>(`/connections/${c}/plan`) : null;
  if (!c || !plan) {
    return (
      <section className="eg-card ep-panel">
        <h1 className="eg-h1">Your plan</h1>
        <p className="eg-muted">Your plan opens once an evaluation is saved and sized.</p>
        <Link className="eg-btn eg-btn--primary" href="/evaluate">New evaluation</Link>
      </section>
    );
  }
  return (
    <>
      <div>
        <div className="eg-overline">Share and audit</div>
        <h1 className="eg-h1">Your plan</h1>
        <p className="eg-muted ep-lede">{plan.client} · {plan.site} · {plan.discom.toUpperCase()}. Share a link that opens without a login, with voice what-if and a PDF; audit the chain of charges behind every landed cost. <Link href={`/results?c=${c}`}>Back to the full results</Link>.</p>
      </div>
      <PlanBuilder connectionId={c} initial={plan} />
    </>
  );
}
