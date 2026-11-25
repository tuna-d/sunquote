import type { Schemas } from "./types";

/** The `type` URNs of the API's `application/problem+json` responses (src/sunquote/api/errors.py). */
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

/** A problem the API answered with, plus the wait its `Retry-After` header asks for. */
export interface ParsedProblem {
  type: string;
  title: string;
  status: number;
  detail: string;
  errors: FieldError[];
  /** Seconds to wait, from `Retry-After` (a 429 carries it); null when absent or unreadable. */
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

/**
 * `Retry-After` as whole seconds from now: it is either a number of seconds or an HTTP date.
 * Null when the header is missing or unreadable.
 */
export function parseRetryAfter(value: string | null, now: Date = new Date()): number | null {
  const text = value?.trim();
  if (!text) {
    return null;
  }
  if (/^\d+$/.test(text)) {
    return Number(text);
  }
  // An HTTP date names its weekday ("Wed, 25 Nov 2026 ..."); `Date.parse` alone accepts "-5".
  const date = /^[A-Za-z]{3},/.test(text) ? Date.parse(text) : Number.NaN;
  if (Number.isNaN(date)) {
    return null;
  }
  return Math.max(0, Math.ceil((date - now.getTime()) / 1000));
}
