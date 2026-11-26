import { type ApiClient, createApiClient } from "./client";
import { PROBLEM_TYPES, parseRetryAfter, problemFrom } from "./problem";
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

const KIND_BY_TYPE: Record<string, AssistantFailure> = {
  [PROBLEM_TYPES.assistantNotConfigured]: "not-configured",
  [PROBLEM_TYPES.assistantUnavailable]: "unavailable",
  [PROBLEM_TYPES.assistantBudgetExhausted]: "budget-exhausted",
  [PROBLEM_TYPES.validation]: "invalid",
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
    const problem = problemFrom(error, response);
    // A 429 is a rate limit even when a proxy answered it without a problem body.
    if (response.status === 429 || problem?.type === PROBLEM_TYPES.rateLimited) {
      const retryAfterSeconds = parseRetryAfter(response.headers.get("Retry-After"));
      return retryAfterSeconds === null
        ? { ok: false, kind: "rate-limited" }
        : { ok: false, kind: "rate-limited", retryAfterSeconds };
    }
    return { ok: false, kind: (problem && KIND_BY_TYPE[problem.type]) || "error" };
  } catch {
    return { ok: false, kind: "network" };
  }
}
