import { describe, expect, it } from "vitest";

import { createApiClient } from "./client";
import { PROBLEM_TYPES, parseRetryAfter, problemFrom } from "./problem";

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

describe("parseRetryAfter", () => {
  it("reads whole seconds", () => {
    expect(parseRetryAfter("120")).toBe(120);
    expect(parseRetryAfter(" 7 ")).toBe(7);
  });

  it("reads an HTTP date as the seconds from now", () => {
    const now = new Date("2026-11-25T10:00:00Z");

    expect(parseRetryAfter("Wed, 25 Nov 2026 10:05:00 GMT", now)).toBe(300);
  });

  it("is zero for a date in the past", () => {
    const now = new Date("2026-11-25T10:00:00Z");

    expect(parseRetryAfter("Wed, 25 Nov 2026 09:00:00 GMT", now)).toBe(0);
  });

  it("is null when the header is missing or unreadable", () => {
    expect(parseRetryAfter(null)).toBeNull();
    expect(parseRetryAfter("")).toBeNull();
    expect(parseRetryAfter("soon")).toBeNull();
    expect(parseRetryAfter("-5")).toBeNull();
  });
});
