import type { Metadata } from "next";

import { QuoteForm } from "@/components/QuoteForm";

export const metadata: Metadata = { title: "Yeni teklif" };

export default function NewQuotePage() {
  return (
    <div className="sheet">
      <QuoteForm />
    </div>
  );
}
