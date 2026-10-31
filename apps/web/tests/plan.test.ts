import { describe, expect, it } from "vitest";
import { Citations } from "../lib/plan";

describe("printed citations", () => {
  it("numbers each document page once, in order of first use", () => {
    const c = new Citations();
    const a = { kind: "order", document_id: "d1", page: 106 } as never;
    const b = { kind: "regulation", document_id: "d2", page: 16 } as never;
    const x = { kind: "assumption", note: "price" } as never;
    expect(c.cite([a, x])).toEqual([1]);
    expect(c.cite([b, a])).toEqual([2, 1]);
    expect(c.notes.length).toBe(2);
  });
});
