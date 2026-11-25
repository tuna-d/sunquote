import type { Metadata } from "next";

import { loadQuoteList } from "@/api/quotes";
import { QuoteListView } from "@/components/QuoteListView";
import { parsePage } from "@/lib/pagination";

export const metadata: Metadata = { title: "Teklifler" };

// The list changes whenever a Quote is created: render on every request.
export const dynamic = "force-dynamic";

export default async function QuotesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const page = parsePage((await searchParams).page);
  const result = await loadQuoteList(page);
  return <QuoteListView result={result} page={page} />;
}
