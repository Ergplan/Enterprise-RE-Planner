import { Evaluation } from "@/components/evaluate/Evaluation";

// The inputs page: one evaluation, six sections, the assistant beside them.
export default async function EvaluatePage({ searchParams }: { searchParams: Promise<{ c?: string }> }) {
  const { c } = await searchParams;
  return (
    <>
      <div>
        <div className="eg-overline">Inputs</div>
        <h1 className="eg-h1">{c ? "Your evaluation" : "New evaluation"}</h1>
        <p className="eg-muted ep-lede">
          Fill the sections in order; required fields are marked *. Drop your bills in section 2 and most of it is read for you.
          Open <b>?</b> beside a field for what it means and where it is used.
        </p>
      </div>
      <Evaluation key={c ?? "new"} connectionId={c ?? null} />
    </>
  );
}
