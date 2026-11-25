import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { assumptions, quote } from "../../test/quoteFixture";
import { QuoteDetailView } from "./QuoteDetailView";

const ID = "cb63fd31-c8cc-4b4f-a0d3-f712d770c106";

function show(stored = quote()) {
  return render(<QuoteDetailView id={ID} result={{ ok: true, quote: stored }} />);
}

/** The value next to a label in a definition list. */
function valueOf(label: string, root: HTMLElement = document.body): HTMLElement {
  const term = within(root).getByText(label, { selector: "dt" });
  return term.nextElementSibling as HTMLElement;
}

describe("QuoteDetailView letterhead", () => {
  it("shows the Quote Number, dates, Customer and place", () => {
    show();

    expect(screen.getByRole("heading", { level: 1, name: "Demo Antalya A" })).toBeInTheDocument();
    expect(valueOf("Teklif no")).toHaveTextContent("SQ-2026-000005");
    expect(valueOf("Tarih")).toHaveTextContent("25.11.2026");
    expect(valueOf("Geçerlilik")).toHaveTextContent("10.12.2026");
    expect(screen.getByText(/Muratpaşa, Antalya/)).toBeInTheDocument();
  });

  it("opens the printable document in a new tab", () => {
    show();

    const links = screen.getAllByRole("link", { name: /Teklif belgesini aç/ });
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(link).toHaveAttribute(
        "href",
        "/api/quotes/cb63fd31-c8cc-4b4f-a0d3-f712d770c106/document",
      );
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    }
  });

  it("introduces the Quote with the stored summary", () => {
    show();
    expect(screen.getByText(/İlk seçenek 6,16 kWp gücünde bir sistemdir/)).toBeInTheDocument();
  });
});

describe("QuoteDetailView System Options", () => {
  it("lays two options out side by side, each in its own card", () => {
    show();

    expect(screen.getByRole("heading", { level: 2, name: "İki seçenek" })).toBeInTheDocument();
    expect(screen.getByRole("article", { name: /Seçenek 1/ })).toBeInTheDocument();
    expect(screen.getByRole("article", { name: /Seçenek 2/ })).toBeInTheDocument();
  });

  it("lays a one-option Quote out with a single card and a single table column", () => {
    show(quote({ options: 1 }));

    expect(screen.getByRole("heading", { level: 2, name: "Sistem seçeneği" })).toBeInTheDocument();
    expect(screen.getAllByRole("article", { name: /^Seçenek/ })).toHaveLength(1);
    const table = screen.getByRole("table", { name: /Tablo 1/ });
    expect(within(table).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "Kalem",
      "Seçenek 1",
    ]);
  });

  it("compares the options in Tablo 1 down to the VAT and the payback", () => {
    show();

    const table = screen.getByRole("table", { name: /Tablo 1/ });
    const cells = (row: RegExp) =>
      within(within(table).getByRole("row", { name: row }))
        .getAllByRole("cell")
        .map((cell) => cell.textContent?.replace(/\xa0/g, " "));
    expect(cells(/Toplam \(KDV dahil\)/)).toEqual(["264.655 TL", "459.614 TL"]);
    expect(cells(/KDV \(%20\)/)).toEqual(["44.109 TL", "76.602 TL"]);
    expect(cells(/Geri ödeme süresi/)).toEqual(["5,9 yıl", "7,6 yıl"]);
  });
});

describe("QuoteDetailView charts", () => {
  it("captions the production figure and gives it a text alternative with every month", () => {
    show();

    expect(screen.getByText(/Şekil 1/)).toBeInTheDocument();
    const data = screen.getByRole("table", { name: /Aylık üretim/ });
    expect(within(data).getAllByRole("row")).toHaveLength(13);
    expect(within(data).getByRole("row", { name: /Temmuz/ })).toHaveTextContent("1.029");
  });

  it("draws one payback figure per option with its price and payback in words", () => {
    show();

    expect(screen.getByText("Şekil 2–3")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /Seçenek 1.*toplam fiyat 264\.655\sTL.*geri ödeme 5,9\syıl/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /Seçenek 2.*toplam fiyat 459\.614\sTL.*geri ödeme 7,6\syıl/ }),
    ).toBeInTheDocument();
  });

  it("draws a single payback figure for a one-option Quote", () => {
    show(quote({ options: 1 }));

    expect(screen.getByText("Şekil 2")).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: /geri ödeme/ })).toHaveLength(1);
  });
});

describe("QuoteDetailView Assumptions", () => {
  function box(): HTMLElement {
    return screen.getByText("Varsayımlar").closest("details")!;
  }

  it("is a collapsible Ek A that starts closed", () => {
    show();
    expect(box()).not.toHaveAttribute("open");
  });

  it("lists the Exchange Rate with its date, the tariff, the ratios, the unit prices, the margin and VAT", () => {
    show();

    const b = box();
    expect(within(b).getByText(/1 USD = 50,6286 TL \(24\.11\.2026, TCMB\)/)).toBeInTheDocument();
    expect(valueOf("Düşük kademe", b)).toHaveTextContent("3,24 TL/kWh · 2.920 kWh");
    expect(valueOf("Yüksek kademe", b)).toHaveTextContent("4,86 TL/kWh · 7.280 kWh");
    expect(valueOf("İhracat fiyatı", b)).toHaveTextContent("1,24 TL/kWh");
    expect(valueOf("Montaj malzemesi", b)).toHaveTextContent("120 $/kWp");
    expect(valueOf("İşçilik", b)).toHaveTextContent("4.000 TL/kWp");
    expect(valueOf("Sabit proje maliyeti", b)).toHaveTextContent("20.000 TL");
    expect(valueOf("Kâr marjı", b)).toHaveTextContent("%25");
    expect(valueOf("KDV", b)).toHaveTextContent("%20");
    expect(valueOf("Panel bozunması", b)).toHaveTextContent("%0,47/yıl");
    expect(valueOf("Sistem kaybı", b)).toHaveTextContent("%14");
    expect(valueOf("Çatı kullanım oranı", b)).toHaveTextContent("%80");
    expect(valueOf("Tarife tarihi", b)).toHaveTextContent("04.04.2026");
  });

  it("says the Exchange Rate was set by hand when it was", () => {
    const stored = quote();
    stored.assumptions = assumptions({
      exchange_rate: {
        base_currency: "USD",
        quote_currency: "TRY",
        rate: "44.5",
        date: "2026-11-24",
        overridden: true,
      },
    });
    show(stored);

    expect(screen.getByText(/1 USD = 44,50 TL \(24\.11\.2026, elle girildi\)/)).toBeInTheDocument();
  });

  it("shows the monthly bill when the consumption came from one", () => {
    const stored = quote();
    stored.assumptions = assumptions({
      consumption_derived_from_bill: true,
      submitted_request: {
        ...assumptions().submitted_request,
        consumption: { monthly_consumption_kwh: null, monthly_bill_try: "7500" },
      },
    });
    show(stored);

    expect(valueOf("Aylık fatura", box())).toHaveTextContent("7.500 TL");
  });
});

describe("QuoteDetailView when the API fails", () => {
  it("says the service could not be reached and offers a retry", () => {
    render(<QuoteDetailView id={ID} result={{ ok: false, reason: "unavailable" }} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Teklif servisine ulaşılamadı");
    expect(screen.getByRole("link", { name: /Tekrar dene/ })).toBeInTheDocument();
  });

  it("says the Quote could not be loaded when the API answered with an error", () => {
    render(<QuoteDetailView id={ID} result={{ ok: false, reason: "error" }} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Teklif yüklenemedi");
  });
});
