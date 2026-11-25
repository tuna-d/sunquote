/**
 * The masthead's sections. A page ticket flips `enabled` when its route exists; until then the
 * section is shown as unavailable instead of linking to a 404.
 *   - /quotes/new: the Quote form (#45, enabled)
 *   - /assistant: the Assistant chat (#46, enabled)
 */
export interface NavItem {
  href: string;
  label: string;
  enabled: boolean;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/quotes", label: "Teklifler", enabled: true },
  { href: "/quotes/new", label: "Yeni teklif", enabled: true },
  { href: "/assistant", label: "Asistan", enabled: true },
];

export function isEnabled(href: string): boolean {
  return NAV_ITEMS.some((item) => item.href === href && item.enabled);
}

/** The enabled section whose path is the longest prefix of `pathname`, if any. */
export function activeHref(pathname: string): string | null {
  const matches = NAV_ITEMS.filter(
    (item) => item.enabled && (pathname === item.href || pathname.startsWith(`${item.href}/`)),
  );
  const best = [...matches].sort((a, b) => b.href.length - a.href.length)[0];
  return best?.href ?? null;
}
