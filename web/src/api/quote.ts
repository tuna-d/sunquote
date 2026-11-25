import { type ApiClient, createApiClient } from "./client";
import type { QuoteResponse } from "./types";

export type QuoteResult =
  | { ok: true; quote: QuoteResponse }
  /**
   * No such Quote. The page calls `notFound()`, which answers a real HTTP 404 only while nothing has
   * streamed yet: do not add a `loading.tsx` above `quotes/[id]` (it would start the response as 200).
   */
  | { ok: false; reason: "not-found" }
  /** `unavailable`: the API could not be reached. `error`: it answered with a failure. */
  | { ok: false; reason: "unavailable" | "error" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** One stored Quote. Never throws: the page renders the failure. */
export async function loadQuote(id: string, client: ApiClient = createApiClient()): Promise<QuoteResult> {
  // The API only has UUID ids; anything else cannot be a Quote, so don't bother it.
  if (!UUID.test(id)) {
    return { ok: false, reason: "not-found" };
  }
  try {
    const { data, response } = await client.GET("/quotes/{quote_id}", {
      params: { path: { quote_id: id } },
    });
    if (response.status === 404) {
      return { ok: false, reason: "not-found" };
    }
    if (data === undefined || !response.ok) {
      return { ok: false, reason: "error" };
    }
    return { ok: true, quote: data };
  } catch {
    return { ok: false, reason: "unavailable" };
  }
}
