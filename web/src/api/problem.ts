/** Helpers for the API's `application/problem+json` errors (RFC 9457). */

export interface ProblemInfo {
  /** The last segment of the problem type URN, e.g. `rate-limited`; null when unreadable. */
  slug: string | null;
  status: number;
  detail: string | null;
  /** Seconds from the `Retry-After` header, when it is a positive whole number. */
  retryAfterSeconds: number | null;
}

export function problemSlug(type: string | undefined): string | null {
  if (!type) {
    return null;
  }
  return type.split(":").pop() || null;
}

export function parseRetryAfter(value: string | null): number | null {
  if (value === null || !/^\d+$/.test(value.trim())) {
    return null;
  }
  const seconds = Number(value);
  return seconds > 0 ? seconds : null;
}

/** Describes a failed response whose body is already parsed (openapi-fetch's `error`). */
export function describeProblem(response: Response, body: unknown): ProblemInfo {
  const fields: { type?: unknown; detail?: unknown } =
    typeof body === "object" && body !== null ? body : {};
  return {
    slug: problemSlug(typeof fields.type === "string" ? fields.type : undefined),
    status: response.status,
    detail: typeof fields.detail === "string" ? fields.detail : null,
    retryAfterSeconds: parseRetryAfter(response.headers.get("Retry-After")),
  };
}

/** Reads a failed response. Never throws: a body that is not JSON just gives nulls. */
export async function readProblem(response: Response): Promise<ProblemInfo> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // not JSON
  }
  return describeProblem(response, body);
}
