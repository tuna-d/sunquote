import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { option, secondOption } from "../../test/quoteFixture";
import { OptionCard } from "./OptionCard";


function renderCard(overrides = option(), number: 1 | 2 = 1) {
  render(<OptionCard option={overrides} number={number} context={{ vatRate: "0.20", lifetimeYears: 25 }} />);
  return screen.getByRole("article", { name: new RegExp(`Seçenek ${number}`) });
}

describe("OptionCard", () => {
  it("shows what the Customer compares: capacity, panels, inverter, production, price, savings, payback", () => {
    const card = renderCard();

    expect(within(card).getByText(`6,16 kWp`)).toBeInTheDocument();
    expect(within(card).getByText(/14 adet/)).toBeInTheDocument();
    expect(within(card).getByText(/Trina Solar Vertex S\+ TSM-NEG9RH\.25 \(440 W\)/)).toBeInTheDocument();
    expect(within(card).getByText(/Huawei SUN2000-5KTL-M1 \(5 kW\)/)).toBeInTheDocument();
    expect(within(card).getByText(`10.087 kWh`)).toBeInTheDocument();
    expect(within(card).getByText(`264.655 TL`)).toBeInTheDocument();
    expect(within(card).getByText("KDV dahil toplam bedel")).toBeInTheDocument();
    expect(within(card).getByText(`42.962 TL`)).toBeInTheDocument();
    expect(within(card).getByText(`5,9 yıl`)).toBeInTheDocument();
  });

  it("leads with the Payback Period as the headline figure, the price after it", () => {
    const card = renderCard();

    const headline = within(card).getByRole("heading", { name: /Seçenek 1/ }).nextElementSibling;
    expect(headline).toHaveTextContent("5,9 yıl");
    expect(headline).toHaveAttribute("data-headline");
    expect(within(card).getByText("Geri ödeme süresi")).toBeInTheDocument();
    const price = within(card).getByText("264.655 TL");
    expect(headline!.compareDocumentPosition(price) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(headline).not.toContainElement(price);
  });

  it("names the sizing strategy of the option", () => {
    expect(within(renderCard()).getByText(/Tüketime göre/)).toBeInTheDocument();
  });

  it("shows the Netted Share, NPV and IRR for the option", () => {
    const card = within(renderCard());

    expect(card.getByText("Faturadan düşen üretim")).toBeInTheDocument();
    expect(card.getByText("%92,5")).toBeInTheDocument();
    expect(card.getByText("Net bugünkü değer")).toBeInTheDocument();
    expect(card.getByText("384.984 TL")).toBeInTheDocument();
    expect(card.getByText("İç verim oranı")).toBeInTheDocument();
    expect(card.getByText("%17,1")).toBeInTheDocument();
  });

  it("shows when IRR is unavailable and still displays a negative NPV", () => {
    const system = option();
    system.savings = {
      ...system.savings,
      npv_try: -45000,
      irr: null,
      payback_period_years: null,
      payback_beyond_lifetime: true,
    };
    const card = within(renderCard(system));

    expect(card.getByText("İç verim oranı")).toBeInTheDocument();
    expect(card.getByText("Hesaplanamıyor")).toBeInTheDocument();
    expect(card.getByText("-45.000 TL")).toBeInTheDocument();
  });

  it("displays a zero IRR as a percentage", () => {
    const system = option();
    system.savings = { ...system.savings, irr: 0 };
    const card = within(renderCard(system));

    expect(card.getByText("%0,0")).toBeInTheDocument();
  });

  it("numbers the second option and shows its own figures", () => {
    const card = renderCard(secondOption(), 2);

    expect(within(card).getByRole("heading", { name: /Seçenek 2/ })).toBeInTheDocument();
    expect(within(card).getByText(`9,68 kWp`)).toBeInTheDocument();
    expect(within(card).getByText(`459.614 TL`)).toBeInTheDocument();
    expect(within(card).getByText(`7,6 yıl`)).toBeInTheDocument();
  });

  it("says so when the price is not recovered within the lifetime", () => {
    const never = option();
    never.savings = { ...never.savings, payback_period_years: null, payback_beyond_lifetime: true };

    const card = renderCard(never);

    const headline = within(card).getByRole("heading", { name: /Seçenek 1/ }).nextElementSibling;
    expect(headline).toHaveTextContent("25 yıl içinde geri ödenmiyor");
    expect(headline).toHaveAttribute("data-headline");
    expect(within(card).getAllByText("25 yıl içinde geri ödenmiyor")).toHaveLength(1);
    expect(within(card).queryByText(/yıl$/)).not.toBeInTheDocument();
  });
});
