import { ProposalsQueue } from "@/components/audit/ProposalsQueue";

// Analysts: every rule change proposed from a client's working, across connections.
export default function ProposalsPage() {
  return (
    <>
      <div>
        <div className="eg-overline">Analyst</div>
        <h1 className="eg-h1">Proposed rule changes</h1>
        <p className="eg-muted ep-lede">Figures in clients&apos; workings that differ from an approved rule. Check the regulation; accept to draft the change (approved with its golden tests) or keep the rule with a note.</p>
      </div>
      <ProposalsQueue />
    </>
  );
}
