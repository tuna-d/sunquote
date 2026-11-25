import { describe, expect, it } from "vitest";

import { sendAssistantMessages } from "./assistant";
import { createApiClient } from "./client";
import type { AssistantResponse } from "./types";

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

const problem = (slug: string, status: number, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify({ type: `urn:sunquote:problem:${slug}`, detail: "x" }), {
    status,
    headers: { "content-type": "application/problem+json", ...headers },
  });

const messages = [{ role: "user" as const, content: "Merhaba" }];

describe("sendAssistantMessages", () => {
  it("posts the whole conversation and returns the reply", async () => {
    const body: AssistantResponse = {
      reply: "Adres?",
      quote: null,
      missing_fields: ["site.address"],
    };
    const { client, requests } = clientAnswering(() => Response.json(body));

    const result = await sendAssistantMessages(messages, client);

    expect(result).toEqual({ ok: true, response: body });
    expect(new URL(requests[0]!.url).pathname).toBe("/assistant/messages");
    expect(await requests[0]!.json()).toEqual({ messages });
  });

  it.each([
    ["assistant-not-configured", 503, "not-configured"],
    ["assistant-unavailable", 503, "unavailable"],
    ["assistant-budget-exhausted", 503, "budget-exhausted"],
    ["validation-error", 422, "invalid"],
  ])("maps %s to %s", async (slug, status, kind) => {
    const { client } = clientAnswering(() => problem(slug, status));
    expect(await sendAssistantMessages(messages, client)).toEqual({ ok: false, kind });
  });

  it("maps 429 to rate-limited with the wait from Retry-After", async () => {
    const { client } = clientAnswering(() =>
      problem("rate-limited", 429, { "Retry-After": "1800" }),
    );
    expect(await sendAssistantMessages(messages, client)).toEqual({
      ok: false,
      kind: "rate-limited",
      retryAfterSeconds: 1800,
    });
  });

  it("maps an unknown failure to error and a dead network to network", async () => {
    const failing = clientAnswering(() => new Response("boom", { status: 500 }));
    expect(await sendAssistantMessages(messages, failing.client)).toEqual({
      ok: false,
      kind: "error",
    });
    const down = clientAnswering(() => {
      throw new TypeError("fetch failed");
    });
    expect(await sendAssistantMessages(messages, down.client)).toEqual({
      ok: false,
      kind: "network",
    });
  });
});
