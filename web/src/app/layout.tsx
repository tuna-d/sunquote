import type { Metadata, Viewport } from "next";
import { Hanken_Grotesk, Newsreader } from "next/font/google";
import Link from "next/link";
import type { ReactNode } from "react";

import { MainNav } from "@/components/MainNav";

import "./globals.css";

// Headings, body and figures. `latin-ext` carries Turkish ğ ş İ ı. The optical-size axis is
// what makes the 44 px headline and the 17 px body both look right (docs/design/tokens-2c.md).
const serif = Newsreader({
  subsets: ["latin", "latin-ext"],
  style: ["normal", "italic"],
  axes: ["opsz"],
  display: "swap",
  variable: "--font-newsreader",
});

// Labels, buttons and chart ticks.
const sans = Hanken_Grotesk({
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-hanken",
});

export const metadata: Metadata = {
  title: { default: "sunquote", template: "%s · sunquote" },
  description: "Güneş paneli kurulumu için otomatik teklif hazırlama.",
};

export const viewport: Viewport = {
  themeColor: "#E5EAF0",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="tr" className={`${serif.variable} ${sans.variable}`}>
      <body>
        <a className="skip" href="#main">
          İçeriğe geç
        </a>
        <header className="mast">
          <Link className="mark" href="/quotes" aria-label="sunquote, teklif listesi">
            sun<span>quote</span>
          </Link>
          <MainNav />
        </header>
        <main id="main">{children}</main>
      </body>
    </html>
  );
}
