import type { components } from "./schema";

/** The API's response and request shapes, generated from its OpenAPI schema (`npm run api:sync`). */
export type Schemas = components["schemas"];
export type QuoteListItem = Schemas["QuoteListItem"];
export type QuoteListResponse = Schemas["QuoteListResponse"];
export type QuoteResponse = Schemas["QuoteResponse"];
export type SystemOptionResponse = Schemas["SystemOptionResponse"];
export type AssumptionsResponse = Schemas["AssumptionsResponse"];
export type MoneyResponse = Schemas["MoneyResponse"];
export type CashFlowRow = Schemas["CashFlowRow"];
