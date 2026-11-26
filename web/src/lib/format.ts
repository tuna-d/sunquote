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

const upToTwoDecimals = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 });
const percentFormat = new Intl.NumberFormat("tr-TR", { style: "percent", maximumFractionDigits: 2 });
const resultPercentFormat = new Intl.NumberFormat("tr-TR", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const oneDecimal = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const rateFormat = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
const coordinateFormat = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 4 });

/** `2026-11-25` -> `25.11.2026`. A calendar date, so no time zone is involved. */
export function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-");
  return `${day}.${month}.${year}`;
}

export function formatKwh(energyKwh: number): string {
  return `${integerFormat.format(energyKwh)}${NBSP}kWh`;
}

/** A tariff price the API sends as a decimal string: `3,24 TL/kWh`. */
export function formatTryPerKwh(priceTryPerKwh: string): string {
  return `${upToTwoDecimals.format(Number(priceTryPerKwh))}${NBSP}TL/kWh`;
}

/** The API rounds the Payback Period to one decimal; this shows it: `5,9 yıl`. */
export function formatPaybackYears(years: number): string {
  return `${oneDecimal.format(years)}${NBSP}yıl`;
}

/** A share the API sends as a number or decimal string, as a percentage: `%25`. */
export function formatShare(share: number | string): string {
  return percentFormat.format(Number(share));
}

/** A result share shown next to another option's (Netted Share, IRR): always one decimal, `%64,0`. */
export function formatResultShare(share: number | string): string {
  return resultPercentFormat.format(Number(share));
}

const CURRENCY_SYMBOLS = { TRY: "TL", USD: "$", EUR: "€" } as const;

/** A unit price with its currency, `76 $`; `per` adds a unit: `120 $/kWp`. */
export function formatMoney(
  money: { amount: string; currency: keyof typeof CURRENCY_SYMBOLS },
  per?: string,
): string {
  const symbol = CURRENCY_SYMBOLS[money.currency];
  return `${upToTwoDecimals.format(Number(money.amount))}${NBSP}${symbol}${per ? `/${per}` : ""}`;
}

/** An exchange rate the API sends as a decimal string: `50,6286`. */
export function formatRate(rate: string): string {
  return rateFormat.format(Number(rate));
}

/** Where the system goes: the submitted address, else the coordinates (`39,9031° K, 32,8597° D`). */
export function formatSite(site: {
  address?: string | null;
  latitude: number | null;
  longitude: number | null;
}): string {
  if (site.address) {
    return site.address;
  }
  if (site.latitude === null || site.longitude === null) {
    return "Konum belirtilmemiş";
  }
  const northSouth = site.latitude >= 0 ? "K" : "G";
  const eastWest = site.longitude >= 0 ? "D" : "B";
  return `${coordinateFormat.format(Math.abs(site.latitude))}° ${northSouth}, ${coordinateFormat.format(Math.abs(site.longitude))}° ${eastWest}`;
}

/** Month labels for chart axes, January first. */
export const MONTH_LABELS = [
  "Oca",
  "Şub",
  "Mar",
  "Nis",
  "May",
  "Haz",
  "Tem",
  "Ağu",
  "Eyl",
  "Eki",
  "Kas",
  "Ara",
] as const;

/** Full month names, for text read aloud and tooltips. */
export const MONTH_NAMES = [
  "Ocak",
  "Şubat",
  "Mart",
  "Nisan",
  "Mayıs",
  "Haziran",
  "Temmuz",
  "Ağustos",
  "Eylül",
  "Ekim",
  "Kasım",
  "Aralık",
] as const;

/** A wait from `Retry-After`, rounded up to the unit it reads best in: `30 dakika`. */
export function formatWait(seconds: number): string {
  const whole = Math.max(1, Math.ceil(seconds));
  if (whole < 60) {
    return `${whole} saniye`;
  }
  if (whole < 3600) {
    return `${Math.ceil(whole / 60)} dakika`;
  }
  return `${Math.ceil(whole / 3600)} saat`;
}
