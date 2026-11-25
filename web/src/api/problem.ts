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

export function parseRetryAfter(value: string | null): number | null {
  if (value === null || !/^\d+$/.test(value.trim())) {
    return null;
  }
  const seconds = Number(value);
  return seconds > 0 ? seconds : null;
}

/** A problem with its full `type` URN, title and field errors. */
export interface ParsedProblem {
  type: string;
  title: string;
  status: number;
  detail: string;
  errors: FieldError[];
  /** Seconds from the `Retry-After` header, when it is a positive whole number. */
  retryAfterSeconds: number | null;
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
