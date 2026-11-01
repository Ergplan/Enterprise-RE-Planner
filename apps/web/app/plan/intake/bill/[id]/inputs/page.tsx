import Link from "next/link";
import { PlanInputsView } from "@/components/intake/PlanInputsView";
import { apiOrNull } from "@/lib/api";
import type { PlanInputs } from "@/lib/reading";

// The hand-off: what RE planning takes from this bill, each figure linked to its page.
export default async function PlanInputsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const inputs = await apiOrNull<PlanInputs>(`/bills/${id}/plan-inputs`);
  if (!inputs) {
    return (
      <section className="eg-card ep-panel">
        <h1 className="eg-h1">Bill not found</h1>
        <Link className="eg-btn eg-btn--primary" href="/plan/intake">Back to bills</Link>
      </section>
    );
  }
  return <PlanInputsView inputs={inputs} />;
}
