import { describe as d, expect, it } from "vitest";
import { describe, leaves, scopeChips, setAt } from "../lib/rulebook";

d("rulebook helpers", () => {
  it("flattens a body to pointers", () => {
    expect(leaves({ a: { b: "1" }, c: ["x", "y"] })).toEqual([
      { pointer: "/a/b", value: "1" },
      { pointer: "/c/0", value: "x" },
      { pointer: "/c/1", value: "y" },
    ]);
  });
  it("sets a value immutably", () => {
    const o = { energy_charge: { base: "7.10" } };
    expect(setAt(o, "/energy_charge/base", "7.20")).toEqual({ energy_charge: { base: "7.20" } });
    expect(o.energy_charge.base).toBe("7.10");
  });
  it("reads schema descriptions", () => {
    const s = { properties: { energy_charge: { properties: { base: { description: "Energy charge" } } } } };
    expect(describe(s, "/energy_charge/base")).toBe("Energy charge");
  });
  it("renders scope as chips", () => {
    expect(scopeChips({ voltage_kv: { min: 11, min_exclusive: true, max: 66 }, category: ["HV-2"], months: [4, 5] })).toEqual([
      "> 11 and ≤ 66 kV",
      "category: HV-2",
      "Apr May",
    ]);
  });
});
