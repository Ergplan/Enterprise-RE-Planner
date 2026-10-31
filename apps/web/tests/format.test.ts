import { describe, expect, it } from "vitest";
import { inr, pageRanges, pdfPageUrl } from "../lib/format";

describe("format", () => {
  it("groups rupees the Indian way", () => {
    expect(inr("391192.06")).toBe("3,91,192.06");
  });
  it("renders page lists as ranges", () => {
    expect(pageRanges([352, 353, 354, 359, 401])).toBe("352–354, 359, 401");
  });
  it("links a PDF at a page through the API proxy", () => {
    expect(pdfPageUrl("abc", 14)).toBe("/api/documents/abc#page=14");
    expect(pdfPageUrl("abc")).toBe("/api/documents/abc");
  });
});
