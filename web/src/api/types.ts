import type { components } from "./schema";

/** The API's response and request shapes, generated from its OpenAPI schema (`npm run api:sync`). */
export type Schemas = components["schemas"];
export type QuoteListItem = Schemas["QuoteListItem"];
export type QuoteListResponse = Schemas["QuoteListResponse"];
export type AssistantResponse = Schemas["AssistantResponse"];
export type MissingField = Schemas["MissingField"];
export type QuoteReference = Schemas["QuoteReference"];
