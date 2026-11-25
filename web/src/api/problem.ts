import type { Schemas } from "./types";

/** Helpers for the API's `application/problem+json` errors (RFC 9457). */

/** The `type` URNs of the API's problem responses (src/sunquote/api/errors.py). */
export const PROBLEM_TYPES = {
  validation: "urn:sunquote:problem:validation-error",
  unsupportedSubscriberGroup: "urn:sunquote:problem:unsupported-subscriber-group",
  noViableSystem: "urn:sunquote:problem:no-viable-system",
  noCompatibleInverter: "urn:sunquote:problem:no-compatible-inverter",
  locationNotSupported: "urn:sunquote:problem:location-not-supported",
  addressNotFound: "urn:sunquote:problem:address-not-found",
  quoteNotFound: "urn:sunquote:problem:quote-not-found",
  upstreamUnavailable: "urn:sunquote:problem:upstream-unavailable",
  rateLimited: "urn:sunquote:problem:rate-limited",
  assistantNotConfigured: "urn:sunquote:problem:assistant-not-configured",
  assistantUnavailable: "urn:sunquote:problem:assistant-unavailable",
  assistantBudgetExhausted: "urn:sunquote:problem:assistant-budget-exhausted",
} as const;

export type FieldError = Schemas["FieldError"];

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

/** A problem with its full `type` URN, title and field errors, for a form that maps them. */
export interface ParsedProblem extends Omit<ProblemInfo, "slug" | "detail"> {
  type: string;
  title: string;
  detail: string;
  errors: FieldError[];
}

/**
 * The problem in a failed response, or null when the body is not a problem (a proxy's HTML page,
 * a framework 500). `body` is what the typed client parsed (`error`); `response` is its
 * `response`, which carries `Retry-After`.
 */
export function problemFrom(
  body: unknown,
  response: Pick<Response, "status" | "headers">,
): ParsedProblem | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const { type, title, status, detail, errors } = body as Record<string, unknown>;
  if (typeof type !== "string") {
    return null;
  }
  return {
    type,
    title: typeof title === "string" ? title : "",
    status: typeof status === "number" ? status : response.status,
    detail: typeof detail === "string" ? detail : "",
    errors: Array.isArray(errors) ? errors.filter(isFieldError) : [],
    retryAfterSeconds: parseRetryAfter(response.headers.get("Retry-After")),
  };
}

function isFieldError(value: unknown): value is FieldError {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const { field, message } = value as Record<string, unknown>;
  return typeof field === "string" && typeof message === "string";
}
