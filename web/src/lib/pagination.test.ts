import { describe, expect, it } from "vitest";

import { pageCount, parsePage } from "./pagination";

describe("parsePage", () => {
  it("defaults to the first page", () => {
    expect(parsePage(undefined)).toBe(1);
  });

  it("reads a positive whole number", () => {
    expect(parsePage("3")).toBe(3);
  });

  it.each(["0", "-2", "abc", "1.5", "", "2e3", " "])("falls back to 1 for %j", (raw) => {
    expect(parsePage(raw)).toBe(1);
  });

  it("uses the first value of a repeated parameter", () => {
    expect(parsePage(["4", "9"])).toBe(4);
  });
});

describe("pageCount", () => {
  it("is at least one so an empty list still has a page", () => {
    expect(pageCount(0, 20)).toBe(1);
  });

  it("rounds up", () => {
    expect(pageCount(20, 20)).toBe(1);
    expect(pageCount(21, 20)).toBe(2);
  });
});
