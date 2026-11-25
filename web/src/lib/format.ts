/**
 * Display helpers for values the API returns raw. They only format; the web app never
 * computes a figure (spec #29). Everything is Turkish: "." groups thousands, "," is the
 * decimal mark, times are Istanbul time.
 */

const NBSP = "\u00a0";

const integerFormat = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 });
const capacityFormat = new Intl.NumberFormat("tr-TR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const dateTimeFormat = new Intl.DateTimeFormat("tr-TR", {
  timeZone: "Europe/Istanbul",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** A whole-lira amount, as the API returns it: `159.821 TL`. */
export function formatTry(amountTry: number): string {
  return `${integerFormat.format(amountTry)}${NBSP}TL`;
}

/** The API rounds capacity to two decimals; this shows them: `3,52 kWp`. */
export function formatCapacityKwp(capacityKwp: number): string {
  return `${capacityFormat.format(capacityKwp)}${NBSP}kWp`;
}

/** `Çankaya / Ankara`, or whichever part is known; `null` when the place is unknown. */
export function formatLocation(district: string | null, province: string | null): string | null {
  const parts = [district, province].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? parts.join(" / ") : null;
}

export function formatOptionCount(count: number): string {
  return `${integerFormat.format(count)} seçenek`;
}

/** `25.11.2026 01:30` in Istanbul time, whatever the machine's own time zone is. */
export function formatCreatedAt(createdAt: string): string {
  const parts = Object.fromEntries(
    dateTimeFormat.formatToParts(new Date(createdAt)).map((part) => [part.type, part.value]),
  );
  return `${parts.day}.${parts.month}.${parts.year} ${parts.hour}:${parts.minute}`;
}
