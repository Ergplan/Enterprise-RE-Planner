import { describe, expect, it } from "vitest";
import { crore, mw, mwh, presets } from "../lib/runs";

const sv = (value: string) => ({ value, unit: "kW", source_refs: [{ kind: "derived" }] }) as never;

describe("step 5 helpers", () => {
  it("formats kW as MW and INR as crore", () => {
    expect(mw(sv("10730.112"))).toBe("10.73");
    expect(crore(sv("31707367.64"))).toBe("₹3.17 cr");
    expect(mw(null)).toBe("—");
    expect(mwh(sv("16810280.5"))).toBe("16,810");
  });
  it("offers three scenarios at the chosen resolution", () => {
    const p = presets("2026-09-01", 15);
    expect(p.map((x) => x.name)).toEqual(["Captive solar", "Hybrid + battery", "Rooftop + solar + battery"]);
    expect(p.every((x) => x.spec.resolution_min === 15 && x.spec.as_of === "2026-09-01")).toBe(true);
  });
});
