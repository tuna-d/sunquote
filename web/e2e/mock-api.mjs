// A stand-in for the sunquote API, for the Playwright smoke test only. It answers the calls the
// smoke test makes with the same shapes as the real API (see src/api/schema.d.ts):
//   POST /quotes        201 with the new Quote's id, or an application/problem+json 422
//   GET  /quotes        the list, newest first
//   GET  /quotes/{id}   the full QuoteResponse of a Quote the mock created, else a 404 problem
// Figures are fixed placeholders: the mock computes nothing, like the web app itself. The Quote
// body is the detail page's Vitest fixture (type-checked against src/api/schema.d.ts there), which
// Node loads as TypeScript by stripping its types.
import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

import { quote as quoteFixture } from "../test/quoteFixture.ts";

const port = Number(process.env.E2E_API_PORT ?? 8210);
const quotes = [];
/** The full QuoteResponse of every Quote created, by id. */
const stored = new Map();

function send(response, status, body, headers = {}) {
  response.writeHead(status, { "content-type": "application/json", ...headers });
  response.end(JSON.stringify(body));
}

function problem(response, slug, status, title, extra = {}) {
  send(
    response,
    status,
    { type: `urn:sunquote:problem:${slug}`, title, status, detail: title, ...extra },
    { "content-type": "application/problem+json" },
  );
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf-8") || "{}");
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://${request.headers.host}`);

  if (request.method === "GET" && url.pathname === "/health") {
    return send(response, 200, { status: "ok" });
  }

  if (request.method === "POST" && url.pathname === "/quotes") {
    const body = await readJson(request);
    if (!body.customer?.name) {
      return problem(response, "validation-error", 422, "Request validation failed", {
        errors: [{ field: "customer.name", message: "required" }],
      });
    }
    // The address the smoke test uses to see the "Address not found" message.
    if (body.site?.address?.includes("Atlantis")) {
      return problem(response, "address-not-found", 422, "Address not found");
    }
    const sequence = quotes.length + 1;
    const id = randomUUID();
    const quoteNumber = `SQ-2026-${String(sequence).padStart(6, "0")}`;
    const createdAt = new Date().toISOString();
    stored.set(
      id,
      quoteFixture({
        id,
        quote_number: quoteNumber,
        created_at: createdAt,
        is_sample: false,
        customer: { name: body.customer.name, phone: null, email: null },
      }),
    );
    const quote = {
      id,
      quote_number: quoteNumber,
      customer_name: body.customer.name,
      created_at: createdAt,
      province: "Ankara",
      district: "Çankaya",
      system_option_count: 2,
      capacity_kwp: 3.52,
      total_try: 159821,
      is_sample: false,
    };
    quotes.unshift(quote);
    return send(response, 201, { id: quote.id, quote_number: quote.quote_number });
  }

  if (request.method === "GET" && url.pathname === "/quotes") {
    const page = Number(url.searchParams.get("page") ?? "1");
    const pageSize = Number(url.searchParams.get("page_size") ?? "20");
    const items = quotes.slice((page - 1) * pageSize, page * pageSize);
    return send(response, 200, { items, total: quotes.length, page, page_size: pageSize });
  }

  if (request.method === "GET" && url.pathname.startsWith("/quotes/")) {
    const found = stored.get(url.pathname.slice("/quotes/".length));
    if (found !== undefined) {
      return send(response, 200, found);
    }
    return problem(response, "quote-not-found", 404, "Quote not found");
  }

  return problem(response, "not-found", 404, "Not found");
});

server.listen(port, "127.0.0.1", () => {
  console.log(`mock API on http://127.0.0.1:${port}`);
});
