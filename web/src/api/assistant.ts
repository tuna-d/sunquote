import { type ApiClient, createApiClient } from "./client";
import { describeProblem } from "./problem";
import type { AssistantResponse } from "./types";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export const MAX_MESSAGES = 20;
export const MAX_MESSAGE_CHARACTERS = 2000;

export type AssistantFailure =
  | "not-configured"
  | "unavailable"
  | "budget-exhausted"
  | "rate-limited"
  | "invalid"
  | "error"
  | "network";

export type AssistantResult =
  | { ok: true; response: AssistantResponse }
  | { ok: false; kind: AssistantFailure; retryAfterSeconds?: number };

const KIND_BY_SLUG: Record<string, AssistantFailure> = {
  "assistant-not-configured": "not-configured",
  "assistant-unavailable": "unavailable",
  "assistant-budget-exhausted": "budget-exhausted",
  "validation-error": "invalid",
};

/** Sends the whole conversation. Never throws: the chat renders the failure. */
export async function sendAssistantMessages(
  messages: ChatMessage[],
  client: ApiClient = createApiClient(),
): Promise<AssistantResult> {
  try {
    const { data, error, response } = await client.POST("/assistant/messages", { body: { messages } });
    if (data !== undefined && response.ok) {
      return { ok: true, response: data };
    }
    const problem = describeProblem(response, error);
    if (problem.status === 429 || problem.slug === "rate-limited") {
      return problem.retryAfterSeconds === null
        ? { ok: false, kind: "rate-limited" }
        : { ok: false, kind: "rate-limited", retryAfterSeconds: problem.retryAfterSeconds };
    }
    return { ok: false, kind: (problem.slug && KIND_BY_SLUG[problem.slug]) || "error" };
  } catch {
    return { ok: false, kind: "network" };
  }
}
