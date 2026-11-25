import { type ApiClient, createApiClient } from "./client";
import { type ParsedProblem, problemFrom } from "./problem";
import type { QuoteRequestBody } from "@/lib/quote-form";

export type CreateQuoteFailure =
  /** The API answered with a problem document. */
  | { ok: false; kind: "problem"; problem: ParsedProblem }
  /** The API could not be reached. */
  | { ok: false; kind: "unavailable" }
  /** The API answered with something that is neither a Quote nor a problem. */
  | { ok: false; kind: "unexpected" };

export type CreateQuoteResult = { ok: true; id: string } | CreateQuoteFailure;

/** `POST /quotes`. Never throws: the form shows the failure. */
export async function createQuote(
  body: QuoteRequestBody,
  client: ApiClient = createApiClient(),
): Promise<CreateQuoteResult> {
  try {
    const { data, error, response } = await client.POST("/quotes", { body });
    if (data !== undefined && response.ok) {
      return { ok: true, id: data.id };
    }
    const problem = problemFrom(error, response);
    return problem === null ? { ok: false, kind: "unexpected" } : { ok: false, kind: "problem", problem };
  } catch {
    return { ok: false, kind: "unavailable" };
  }
}
