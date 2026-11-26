import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DemoBanner } from "./demo-banner";

describe("DemoBanner", () => {
  it("says the demo is public, asks for no real personal data and says Quotes are deleted", () => {
    render(<DemoBanner />);

    const note = screen.getByRole("note", { name: "Herkese açık demo" });
    expect(note).toHaveTextContent("Gerçek kişisel veri");
    expect(note).toHaveTextContent("girmeyin");
    expect(note).toHaveTextContent("her gece silinir");
  });
});
