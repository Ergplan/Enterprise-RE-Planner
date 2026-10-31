import { describe, expect, it } from "vitest";
import { hhmm, inr, uniqueRefs } from "../lib/cost";

describe("cost helpers", () => {
  it("formats rupees in the Indian grouping", () => {
    expect(inr("1402050", 2)).toBe("₹14,02,050.00");
    expect(inr(null)).toBe("—");
  });
  it("names 15-minute blocks", () => {
    expect(hhmm(0)).toBe("00:00");
    expect(hhmm(81)).toBe("20:15");
  });
  it("puts document citations first and drops duplicates", () => {
    const order = { kind: "order" as const, document_id: "d", page: 100, quote: "q" };
    const bill = { kind: "bill" as const, bill_id: "b", field_path: "energy.kvah" };
    const refs = uniqueRefs([
      { value: "1", unit: "INR", source_refs: [bill, order] },
      { value: "2", unit: "INR", source_refs: [order] },
    ]);
    expect(refs.map((r) => r.kind)).toEqual(["order", "bill"]);
  });
});
