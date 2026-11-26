import createClient from "openapi-fetch";

import type { paths } from "./schema";

export type ApiClient = ReturnType<typeof createApiClient>;

/**
 * Where the API is for the code that is running.
 *
 * In the browser it is `/api` on the web app's own origin: a Next rewrite forwards it to
 * the API, so there is no CORS. On the server (pages render there) the rewrite is not
 * available, so the server talks to `SUNQUOTE_API_URL` directly.
 */
export function apiBaseUrl(): string {
  if (typeof window !== "undefined") {
    return "/api";
  }
  return (process.env.SUNQUOTE_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
}

/** The typed API client. Tests pass their own `baseUrl` and `fetch`. */
export function createApiClient(options: { baseUrl?: string; fetch?: (request: Request) => Promise<Response> } = {}) {
  return createClient<paths>({
    baseUrl: options.baseUrl ?? apiBaseUrl(),
    ...(options.fetch ? { fetch: options.fetch } : {}),
    // Quotes change under the Sales Rep's feet; never serve a stale list.
    cache: "no-store",
  });
}
