import { describe, expect, it } from "vitest";

import { createApiClient } from "./client";
import { loadQuoteList, QUOTE_LIST_PAGE_SIZE } from "./quotes";
import type { QuoteListResponse } from "./types";

const body: QuoteListResponse = {
  items: [],
  page: 2,
  page_size: QUOTE_LIST_PAGE_SIZE,
  total: 0,
};

function clientAnswering(respond: (request: Request) => Response | Promise<Response>) {
  const requests: Request[] = [];
  const client = createApiClient({
    baseUrl: "http://api.test",
    fetch: async (request: Request) => {
      requests.push(request);
      return respond(request);
    },
  });
  return { client, requests };
}

describe("loadQuoteList", () => {
  it("asks for the requested page and returns the API's page unchanged", async () => {
    const { client, requests } = clientAnswering(() => Response.json(body));

    const result = await loadQuoteList(2, client);

    expect(result).toEqual({ ok: true, list: body });
    expect(new URL(requests[0]!.url).pathname).toBe("/quotes");
    expect(new URL(requests[0]!.url).searchParams.get("page")).toBe("2");
    expect(new URL(requests[0]!.url).searchParams.get("page_size")).toBe(
      String(QUOTE_LIST_PAGE_SIZE),
    );
  });

  it("reports an API error response as an error", async () => {
    const { client } = clientAnswering(
      () =>
        new Response(JSON.stringify({ type: "about:blank", status: 500 }), {
          status: 500,
          headers: { "content-type": "application/problem+json" },
        }),
    );

    expect(await loadQuoteList(1, client)).toEqual({ ok: false, reason: "error" });
  });

  it("reports an unreachable API as unavailable", async () => {
    const { client } = clientAnswering(() => {
      throw new TypeError("fetch failed");
    });

    expect(await loadQuoteList(1, client)).toEqual({ ok: false, reason: "unavailable" });
  });
});
