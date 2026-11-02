"use client";

import { useCallback, useEffect, useState } from "react";
import { analystFetch } from "@/lib/analyst";
import type { Proposal } from "@/lib/audit";
import { ProposalQueue } from "./AuditScreen";

export function ProposalsQueue() {
  const [items, setItems] = useState<Proposal[]>([]);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const [open, accepted, rejected] = await Promise.all(
        ["open", "accepted", "rejected"].map((st) => analystFetch<Proposal[]>(`/rule-proposals?status=${st}`)),
      );
      setItems([...open, ...accepted, ...rejected]);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function act<T>(fn: () => Promise<T>): Promise<T | null> {
    try {
      const out = await fn();
      await load();
      return out;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  }

  return (
    <>
      {error && <p className="ep-error">{error}</p>}
      <ProposalQueue proposals={items} onAct={act} />
    </>
  );
}
