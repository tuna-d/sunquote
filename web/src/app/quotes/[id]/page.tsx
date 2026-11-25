import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { loadQuote } from "@/api/quote";
import { QuoteDetailView } from "@/components/QuoteDetailView";

export const metadata: Metadata = { title: "Teklif" };

// A stored Quote never changes, but the Quote may not exist yet or any more: render on request.
export const dynamic = "force-dynamic";

export default async function QuotePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const result = await loadQuote(id);
  if (!result.ok && result.reason === "not-found") {
    notFound();
  }
  return <QuoteDetailView id={id} result={result} />;
}
