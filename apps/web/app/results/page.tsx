import Link from "next/link";
import { Results } from "@/components/results/Results";

// The results: the full report for one evaluation, scenario by scenario.
export default async function ResultsPage({ searchParams }: { searchParams: Promise<{ c?: string; s?: string }> }) {
  const { c, s } = await searchParams;
  if (!c) {
    return (
      <section className="eg-card ep-panel">
        <h1 className="eg-h1">Results</h1>
        <p className="eg-muted">Pick an evaluation first.</p>
        <Link className="eg-btn eg-btn--primary" href="/">Your evaluations</Link>
      </section>
    );
  }
  return (
    <>
      <div>
        <div className="eg-overline">Results</div>
        <h1 className="eg-h1">Your plan, in full</h1>
      </div>
      <Results key={`${c}:${s ?? ""}`} connectionId={c} scenarioId={s ?? null} />
    </>
  );
}
