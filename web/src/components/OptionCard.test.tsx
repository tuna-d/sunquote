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

  it("names the sizing strategy of the option", () => {
    expect(within(renderCard()).getByText(/Tüketime göre/)).toBeInTheDocument();
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

    expect(within(card).getByText("25 yıl içinde geri ödenmiyor")).toBeInTheDocument();
    expect(within(card).queryByText(/yıl$/)).not.toBeInTheDocument();
  });
});
