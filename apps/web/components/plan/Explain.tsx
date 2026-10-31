"use client";

import { useState } from "react";

// A short explanation drafted by the model from the sourced numbers beside it; it never replaces them.
export function Explain({ token, scenarioId, item }: { token: string; scenarioId: string; item: string }) {
  const [text, setText] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "error">("idle");
  async function go() {
    setState("busy");
    try {
      const r = await fetch(`/api/p/${token}/explain`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario_id: scenarioId, item }) });
      if (!r.ok) throw new Error();
      setText(((await r.json()) as { text: string }).text);
      setState("idle");
    } catch {
      setState("error");
    }
  }
  if (text) return <p className="ep-explain"><span className="eg-chip">explanation</span> {text}</p>;
  return (
    <button className="eg-btn eg-btn--ghost eg-btn--sm ep-noprint" disabled={state === "busy"} onClick={go}>
      {state === "busy" ? "Writing…" : state === "error" ? "Explanation unavailable" : "Explain"}
    </button>
  );
}
