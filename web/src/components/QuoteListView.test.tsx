import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { QuoteListResult } from "@/api/quotes";
import type { QuoteListItem } from "@/api/types";

import { QuoteListView } from "./QuoteListView";

function item(overrides: Partial<QuoteListItem> = {}): QuoteListItem {
  return {
    id: "6f1c1a52-0000-4000-8000-000000000001",
    quote_number: "SQ-2026-000001",
    created_at: "2026-11-24T22:30:00Z",
    is_sample: false,
    customer_name: "Elif Yıldırım",
    district: "Çankaya",
    province: "Ankara",
    system_option_count: 2,
    capacity_kwp: 3.52,
    total_try: 159821,
    ...overrides,
  };
}

function loaded(items: QuoteListItem[], page = 1, total = items.length): QuoteListResult {
  return { ok: true, list: { items, page, page_size: 20, total } };
}

describe("QuoteListView with Quotes", () => {
  it("shows what the Sales Rep needs to recognise a Quote", () => {
    render(<QuoteListView result={loaded([item()])} page={1} />);

    const row = screen.getByRole("row", { name: /Elif Yıldırım/ });
    expect(within(row).getByRole("link", { name: "Elif Yıldırım" })).toHaveAttribute(
      "href",
      "/quotes/6f1c1a52-0000-4000-8000-000000000001",
    );
    expect(within(row).getByText("Çankaya / Ankara")).toBeInTheDocument();
    expect(within(row).getByText("SQ-2026-000001")).toBeInTheDocument();
    expect(within(row).getByText("25.11.2026 01:30")).toBeInTheDocument();
    expect(within(row).getByText("2 seçenek")).toBeInTheDocument();
    expect(within(row).getByText("3,52 kWp")).toBeInTheDocument();
    expect(within(row).getByText("159.821 TL")).toBeInTheDocument();
  });

  it("keeps the API's order, newest first", () => {
    render(
      <QuoteListView
        result={loaded([
          item({ id: "a", customer_name: "Yeni Müşteri" }),
          item({ id: "b", customer_name: "Eski Müşteri" }),
        ])}
        page={1}
      />,
    );

    const names = screen.getAllByRole("link", { name: /Müşteri/ }).map((a) => a.textContent);
    expect(names).toEqual(["Yeni Müşteri", "Eski Müşteri"]);
  });

  it("badges sample Quotes and only those", () => {
    render(
      <QuoteListView
        result={loaded([
          item({ id: "a", customer_name: "Örnek Ev", is_sample: true }),
          item({ id: "b", customer_name: "Gerçek Ev", is_sample: false }),
        ])}
        page={1}
      />,
    );

    expect(within(screen.getByRole("row", { name: /Örnek Ev/ })).getByText("Örnek")).toBeVisible();
    expect(within(screen.getByRole("row", { name: /Gerçek Ev/ })).queryByText("Örnek")).toBeNull();
  });

  it("says so when the place is not known", () => {
    render(<QuoteListView result={loaded([item({ district: null, province: null })])} page={1} />);

    expect(screen.getByText("Konum belirtilmemiş")).toBeInTheDocument();
  });

  it("states that capacity and price are the first option's", () => {
    render(<QuoteListView result={loaded([item()])} page={1} />);

    expect(screen.getByText(/ilk seçeneğe aittir/i)).toBeInTheDocument();
  });
});

describe("QuoteListView paging", () => {
  it("links to the next page from the first, and not to a previous one", () => {
    render(<QuoteListView result={loaded([item()], 1, 45)} page={1} />);

    expect(screen.getByText("Sayfa 1 / 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Sonraki/ })).toHaveAttribute("href", "/quotes?page=2");
    expect(screen.queryByRole("link", { name: /Önceki/ })).toBeNull();
  });

  it("links both ways from a middle page", () => {
    render(<QuoteListView result={loaded([item()], 2, 45)} page={2} />);

    expect(screen.getByRole("link", { name: /Önceki/ })).toHaveAttribute("href", "/quotes");
    expect(screen.getByRole("link", { name: /Sonraki/ })).toHaveAttribute("href", "/quotes?page=3");
  });

  it("has no next link on the last page", () => {
    render(<QuoteListView result={loaded([item()], 3, 45)} page={3} />);

    expect(screen.queryByRole("link", { name: /Sonraki/ })).toBeNull();
  });

  it("shows no pager for a single page", () => {
    render(<QuoteListView result={loaded([item()])} page={1} />);

    expect(screen.queryByRole("navigation", { name: "Sayfalar" })).toBeNull();
  });

  it("sends the reader back to the first page when the page is past the end", () => {
    render(<QuoteListView result={loaded([], 9, 45)} page={9} />);

    expect(screen.getByText("Bu sayfada teklif yok")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /İlk sayfaya dön/ })).toHaveAttribute("href", "/quotes");
  });
});

describe("QuoteListView without Quotes", () => {
  it("explains the empty list", () => {
    render(<QuoteListView result={loaded([])} page={1} />);

    expect(screen.getByRole("heading", { name: "Henüz teklif yok" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("QuoteListView failures", () => {
  it("tells the Sales Rep the API is unreachable, as an alert", () => {
    render(<QuoteListView result={{ ok: false, reason: "unavailable" }} page={1} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Teklif servisine ulaşılamadı");
    expect(screen.getByRole("link", { name: /Tekrar dene/ })).toHaveAttribute("href", "/quotes");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("tells the Sales Rep the API failed, and retries the same page", () => {
    render(<QuoteListView result={{ ok: false, reason: "error" }} page={3} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Teklifler yüklenemedi");
    expect(screen.getByRole("link", { name: /Tekrar dene/ })).toHaveAttribute(
      "href",
      "/quotes?page=3",
    );
  });
});
