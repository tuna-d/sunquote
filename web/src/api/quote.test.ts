import { describe, expect, it } from "vitest";

import { quote } from "../../test/quoteFixture";
import { createApiClient } from "./client";
import { loadQuote } from "./quote";

const ID = "cb63fd31-c8cc-4b4f-a0d3-f712d770c106";

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

function problem(status: number) {
  return new Response(JSON.stringify({ type: "about:blank", status }), {
    status,
    headers: { "content-type": "application/problem+json" },
  });
}

describe("loadQuote", () => {
  it("asks for the Quote by id and returns it unchanged", async () => {
    const stored = quote();
    const { client, requests } = clientAnswering(() => Response.json(stored));

    const result = await loadQuote(ID, client);

    expect(result).toEqual({ ok: true, quote: stored });
    expect(new URL(requests[0]!.url).pathname).toBe(`/quotes/${ID}`);
  });

  it("reports an unknown id as not found", async () => {
    const { client } = clientAnswering(() => problem(404));
    expect(await loadQuote(ID, client)).toEqual({ ok: false, reason: "not-found" });
  });

  it("reports an id that is not a UUID as not found, without asking the API", async () => {
    const { client, requests } = clientAnswering(() => problem(422));
    expect(await loadQuote("abc", client)).toEqual({ ok: false, reason: "not-found" });
    expect(requests).toHaveLength(0);
  });

  it("reports an API failure as an error", async () => {
    const { client } = clientAnswering(() => problem(500));
    expect(await loadQuote(ID, client)).toEqual({ ok: false, reason: "error" });
  });

  it("reports an unreachable API as unavailable", async () => {
    const { client } = clientAnswering(() => {
      throw new TypeError("fetch failed");
    });
    expect(await loadQuote(ID, client)).toEqual({ ok: false, reason: "unavailable" });
  });
});
