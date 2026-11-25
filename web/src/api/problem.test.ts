import { describe, expect, it } from "vitest";

import { createApiClient } from "./client";
import { PROBLEM_TYPES, parseRetryAfter, problemFrom, problemSlug, readProblem } from "./problem";

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

function problemResponse(body: unknown, status: number, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/problem+json", ...headers },
  });
}

describe("problemFrom", () => {
  it("reads the type, status, detail and the field errors of a validation problem", () => {
    const response = problemResponse({}, 422);
    const problem = problemFrom(
      {
        type: PROBLEM_TYPES.validation,
        title: "Request validation failed",
        status: 422,
        detail: "1 field(s) failed validation: customer.name",
        errors: [{ field: "customer.name", message: "String should have at least 1 character" }],
      },
      response,
    );

    expect(problem).toMatchObject({
      type: "urn:sunquote:problem:validation-error",
      status: 422,
      errors: [{ field: "customer.name", message: "String should have at least 1 character" }],
      retryAfterSeconds: null,
    });
  });

  it("has an empty error list when the problem carries no field errors", () => {
    const problem = problemFrom(
      { type: PROBLEM_TYPES.noViableSystem, title: "t", status: 422, detail: "d" },
      problemResponse({}, 422),
    );

    expect(problem?.errors).toEqual([]);
  });

  it("takes the wait of a rate-limited problem from Retry-After", () => {
    const problem = problemFrom(
      { type: PROBLEM_TYPES.rateLimited, title: "Rate limit reached", status: 429, detail: "d" },
      problemResponse({}, 429, { "Retry-After": "1800" }),
    );

    expect(problem?.type).toBe("urn:sunquote:problem:rate-limited");
    expect(problem?.retryAfterSeconds).toBe(1800);
  });

  it("is null for a body that is not a problem", () => {
    expect(problemFrom(undefined, problemResponse({}, 500))).toBeNull();
    expect(problemFrom("Internal Server Error", problemResponse({}, 500))).toBeNull();
    expect(problemFrom({ detail: "Not Found" }, problemResponse({}, 404))).toBeNull();
  });

  it("works on what the typed client returns for an application/problem+json body", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test",
      fetch: async () =>
        problemResponse(
          { type: PROBLEM_TYPES.rateLimited, title: "Rate limit reached", status: 429, detail: "d" },
          429,
          { "Retry-After": "90" },
        ),
    });

    const { error, response } = await client.GET("/quotes", {});

    expect(problemFrom(error, response)).toMatchObject({
      type: PROBLEM_TYPES.rateLimited,
      retryAfterSeconds: 90,
    });
  });
});
