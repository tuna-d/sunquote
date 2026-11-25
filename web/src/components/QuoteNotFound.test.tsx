import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QuoteNotFound } from "./QuoteNotFound";

describe("QuoteNotFound", () => {
  it("tells the Sales Rep in Turkish that the Quote does not exist", () => {
    render(<QuoteNotFound />);

    expect(screen.getByRole("heading", { level: 1, name: "Teklif bulunamadı" })).toBeInTheDocument();
    expect(screen.getByText(/silinmiş olabilir/)).toBeInTheDocument();
  });

  it("links back to the Quote list", () => {
    render(<QuoteNotFound />);

    expect(screen.getByRole("link", { name: /Tekliflere dön/ })).toHaveAttribute("href", "/quotes");
  });
});
