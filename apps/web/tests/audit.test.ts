import { describe, expect, it } from "vitest";
import { fmt, linesByKey, type Working, type WorkingLine } from "../lib/audit";

const line = (id: string, key: string | null): WorkingLine => ({
  id, working_id: "w", chain_key: key, compare: "value", label: id, value: "3.20", scale: "units", unit: "INR/kWh",
  page: 1, quote: "PPA 3.20", theirs: "3.2", ours: "3.5", ours_unit: "INR/kWh", difference: "-0.3", status: "differs",
  note: null, kind: "yours", created_by: "c", created_at: "2026-11-02T00:00:00Z",
});

describe("audit helpers", () => {
  it("keeps the latest line set against each link", () => {
    const w = (lines: WorkingLine[]): Working => ({ id: "w", connection_id: "c", filename: "f.csv", pages: [], uploaded_by: "c", created_at: "", lines });
    const by = linesByKey([w([line("a", "s.price.price"), line("x", null)]), w([line("b", "s.price.price")])]);
    expect(Object.keys(by)).toEqual(["s.price.price"]);
    expect(by["s.price.price"].id).toBe("b");
  });
  it("formats each unit the chain uses", () => {
    expect(fmt("3.5", "INR/kWh")).toBe("₹3.500");
    expect(fmt("41236770.27", "INR")).toBe("₹4,12,36,770");
    expect(fmt("4.5", "percent")).toBe("4.5%");
    expect(fmt(null, "INR")).toBe("—");
    expect(fmt("-0.38", "INR/kWh")).toBe("−₹0.380");
  });
});
