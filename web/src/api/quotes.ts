import { type ApiClient, createApiClient } from "./client";
import type { QuoteListResponse } from "./types";

export const QUOTE_LIST_PAGE_SIZE = 20;

export type QuoteListResult =
  | { ok: true; list: QuoteListResponse }
  /** `unavailable`: the API could not be reached. `error`: it answered with a failure. */
  | { ok: false; reason: "unavailable" | "error" };

/** One page of stored Quotes, newest first. Never throws: the page renders the failure. */
export async function loadQuoteList(
  page: number,
  client: ApiClient = createApiClient(),
): Promise<QuoteListResult> {
  try {
    const { data, response } = await client.GET("/quotes", {
      params: { query: { page, page_size: QUOTE_LIST_PAGE_SIZE } },
    });
    if (data === undefined || !response.ok) {
      return { ok: false, reason: "error" };
    }
    return { ok: true, list: data };
  } catch {
    return { ok: false, reason: "unavailable" };
  }
}
