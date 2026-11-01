import Link from "next/link";
import { BillTheatre } from "@/components/intake/BillTheatre";
import { apiOrNull } from "@/lib/api";
import type { BillReading } from "@/lib/reading";

// The reading view of one bill: the page beside what billx read, value by value.
export default async function BillReadingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const reading = await apiOrNull<BillReading>(`/bills/${id}/reading`);
  if (!reading) {
    return (
      <section className="eg-card ep-panel">
        <h1 className="eg-h1">Bill not found</h1>
        <p className="eg-muted">This bill was not found, or it belongs to another client.</p>
        <Link className="eg-btn eg-btn--primary" href="/plan/intake">Back to bills</Link>
      </section>
    );
  }
  return <BillTheatre initial={reading} />;
}
