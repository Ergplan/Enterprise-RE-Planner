import { describe, expect, it } from "vitest";
import { errorText, fieldLabel, monthLabel, refHref } from "../lib/intake";

describe("intake helpers", () => {
  it("labels bill fields and ToD slots", () => {
    expect(fieldLabel("demand.max_kva")).toBe("Recorded maximum demand");
    expect(fieldLabel("energy.tod.1.kwh", ["Tod-1", "Tod-2"])).toBe("ToD energy · Tod-2");
    expect(fieldLabel("energy.tod.4.kwh")).toBe("ToD energy · slot 5");
    expect(fieldLabel("x.y")).toBe("x.y");
  });
  it("links a bill ref to the stored bill page and a document ref to the viewer", () => {
    expect(refHref({ kind: "bill", bill_id: "b1", field_path: "energy.kwh", url: "/bills/b1/file#page=2" })).toBe("/api/bills/b1/file#page=2");
    expect(refHref({ kind: "bill", bill_id: "b1", field_path: "energy.kwh" })).toBe("/api/bills/b1/file");
    expect(refHref({ kind: "order", document_id: "d", page: 3, quote: "q" })).toBe("/api/documents/d#page=3");
    expect(refHref({ kind: "assumption", note: "n" })).toBeNull();
  });
  it("reads API errors", () => {
    expect(errorText(422, { detail: "bad" })).toBe("bad");
    expect(errorText(422, { detail: [{ loc: ["body", "intake", "state"], msg: "wrong" }] })).toBe("intake.state: wrong");
    expect(errorText(409, { detail: { message: "overlap" } })).toBe("overlap");
    expect(errorText(500, null)).toBe("Request failed (500)");
  });
  it("formats months", () => {
    expect(monthLabel("2026-06-01")).toMatch(/Jun.*2026/);
  });
});
