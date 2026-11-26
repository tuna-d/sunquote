"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { activeHref, NAV_ITEMS } from "@/lib/navigation";

export function MainNav() {
  const active = activeHref(usePathname());

  return (
    <nav aria-label="Ana gezinme" className="mast-nav">
      {NAV_ITEMS.map((item) =>
        item.enabled ? (
          <Link
            key={item.href}
            href={item.href}
            aria-current={item.href === active ? "page" : undefined}
          >
            {item.label}
          </Link>
        ) : (
          <span key={item.href} aria-disabled="true" title="Yakında">
            {item.label}
          </span>
        ),
      )}
    </nav>
  );
}
