import { describe, expect, it } from "vitest";

import { parseRetryAfter, problemSlug, readProblem } from "./problem";

describe("problemSlug", () => {
  it("takes the last segment of the problem type URN", () => {
    expect(problemSlug("urn:sunquote:problem:rate-limited")).toBe("rate-limited");
    expect(problemSlug(undefined)).toBeNull();
  });
});

describe("parseRetryAfter", () => {
  it("reads whole seconds and ignores anything else", () => {
    expect(parseRetryAfter("120")).toBe(120);
    expect(parseRetryAfter(null)).toBeNull();
    expect(parseRetryAfter("Wed, 21 Oct 2026 07:28:00 GMT")).toBeNull();
    expect(parseRetryAfter("0")).toBeNull();
  });
});

describe("readProblem", () => {
  it("reads the type, status and Retry-After of a problem response", async () => {
    const response = new Response(
      JSON.stringify({ type: "urn:sunquote:problem:rate-limited", detail: "slow down" }),
      { status: 429, headers: { "content-type": "application/problem+json", "Retry-After": "90" } },
    );
    expect(await readProblem(response)).toEqual({
      slug: "rate-limited",
      status: 429,
      detail: "slow down",
      retryAfterSeconds: 90,
    });
  });

  it("copes with a body that is not JSON", async () => {
    const response = new Response("<html>bad gateway</html>", { status: 502 });
    expect(await readProblem(response)).toEqual({
      slug: null,
      status: 502,
      detail: null,
      retryAfterSeconds: null,
    });
  });
});
