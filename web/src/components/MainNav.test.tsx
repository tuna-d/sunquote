import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const pathname = vi.hoisted(() => ({ current: "/quotes" }));
vi.mock("next/navigation", () => ({ usePathname: () => pathname.current }));

import { NAV_ITEMS } from "@/lib/navigation";

import { MainNav } from "./MainNav";

describe("MainNav", () => {
  it("marks the section the Sales Rep is in", () => {
    pathname.current = "/quotes";
    render(<MainNav />);

    expect(screen.getByRole("link", { name: "Teklifler" })).toHaveAttribute("aria-current", "page");
  });

  it("keeps the Quotes section marked on a Quote's own page", () => {
    pathname.current = "/quotes/6f1c1a52";
    render(<MainNav />);

    expect(screen.getByRole("link", { name: "Teklifler" })).toHaveAttribute("aria-current", "page");
  });

  it("names the three sections in order, in a labelled navigation", () => {
    pathname.current = "/quotes";
    render(<MainNav />);

    const nav = screen.getByRole("navigation", { name: "Ana gezinme" });
    expect(nav).toHaveTextContent(/Teklifler.*Yeni teklif.*Asistan/);
  });

  it("shows sections whose page is not built yet as unavailable, not as dead links", () => {
    pathname.current = "/quotes";
    render(<MainNav />);

    for (const item of NAV_ITEMS) {
      if (item.enabled) {
        expect(screen.getByRole("link", { name: item.label })).toHaveAttribute("href", item.href);
      } else {
        expect(screen.queryByRole("link", { name: item.label })).toBeNull();
        expect(screen.getByText(item.label)).toHaveAttribute("aria-disabled", "true");
      }
    }
  });

  it("links the Assistant", () => {
    pathname.current = "/quotes";
    render(<MainNav />);

    expect(screen.getByRole("link", { name: "Asistan" })).toHaveAttribute("href", "/assistant");
  });
});
