import { describe, expect, it } from "vitest";

import {
  formatCapacityKwp,
  formatCreatedAt,
  formatDate,
  formatKwh,
  formatMoney,
  formatPaybackYears,
  formatRate,
  formatShare,
  formatSite,
  formatTryPerKwh,
  MONTH_LABELS,
  formatLocation,
  formatOptionCount,
  formatTry,
} from "./format";

const NBSP = "\u00a0";

describe("formatTry", () => {
  it("groups thousands with a dot and appends TL after a non-breaking space", () => {
    expect(formatTry(159821)).toBe(`159.821${NBSP}TL`);
  });

  it("shows small and zero amounts without a separator", () => {
    expect(formatTry(950)).toBe(`950${NBSP}TL`);
    expect(formatTry(0)).toBe(`0${NBSP}TL`);
  });

  it("groups millions", () => {
    expect(formatTry(1661507)).toBe(`1.661.507${NBSP}TL`);
  });
});

describe("formatCapacityKwp", () => {
  it("uses a decimal comma and always two decimals", () => {
    expect(formatCapacityKwp(3.52)).toBe(`3,52${NBSP}kWp`);
    expect(formatCapacityKwp(5)).toBe(`5,00${NBSP}kWp`);
    expect(formatCapacityKwp(10.56)).toBe(`10,56${NBSP}kWp`);
  });
});

describe("formatLocation", () => {
  it("joins district and province", () => {
    expect(formatLocation("Çankaya", "Ankara")).toBe("Çankaya / Ankara");
  });

  it("shows the province alone when there is no district", () => {
    expect(formatLocation(null, "Ankara")).toBe("Ankara");
  });

  it("shows the district alone when there is no province", () => {
    expect(formatLocation("Çankaya", null)).toBe("Çankaya");
  });

  it("returns null when the place is unknown", () => {
    expect(formatLocation(null, null)).toBeNull();
  });
});

describe("formatOptionCount", () => {
  it("names the count in Turkish", () => {
    expect(formatOptionCount(1)).toBe("1 seçenek");
    expect(formatOptionCount(2)).toBe("2 seçenek");
  });
});

describe("formatCreatedAt", () => {
  it("shows the Istanbul wall-clock date and time, day first", () => {
    // 22:30 UTC is 01:30 the next day in Istanbul (UTC+3, no daylight saving).
    expect(formatCreatedAt("2026-11-24T22:30:00Z")).toBe("25.11.2026 01:30");
  });

  it("does not depend on the machine's time zone for an offset timestamp", () => {
    expect(formatCreatedAt("2026-06-01T09:05:00+03:00")).toBe("01.06.2026 09:05");
  });
});

describe("formatDate", () => {
  it("writes an ISO calendar date day first, without any time zone shift", () => {
    expect(formatDate("2026-11-25")).toBe("25.11.2026");
    expect(formatDate("2026-01-05")).toBe("05.01.2026");
  });
});

describe("formatKwh and formatTryPerKwh", () => {
  it("groups thousands with a dot", () => {
    expect(formatKwh(10087)).toBe(`10.087${NBSP}kWh`);
    expect(formatKwh(604)).toBe(`604${NBSP}kWh`);
  });

  it("shows a tariff price given as a decimal string with a decimal comma", () => {
    expect(formatTryPerKwh("3.24")).toBe(`3,24${NBSP}TL/kWh`);
    expect(formatTryPerKwh("1.24")).toBe(`1,24${NBSP}TL/kWh`);
  });
});

describe("formatPaybackYears", () => {
  it("shows the API's one-decimal years with a decimal comma", () => {
    expect(formatPaybackYears(5.9)).toBe(`5,9${NBSP}yıl`);
    expect(formatPaybackYears(10)).toBe(`10,0${NBSP}yıl`);
  });
});

describe("formatShare", () => {
  it("writes a share given as a decimal string as a percentage, keeping needed decimals", () => {
    expect(formatShare("0.20")).toBe("%20");
    expect(formatShare("0.25")).toBe("%25");
    expect(formatShare("0.0047")).toBe("%0,47");
    expect(formatShare("0.056")).toBe("%5,6");
    expect(formatShare("0")).toBe("%0");
  });
});

describe("formatMoney", () => {
  it("shows an amount with its currency", () => {
    expect(formatMoney({ amount: "76", currency: "USD" })).toBe(`76${NBSP}$`);
    expect(formatMoney({ amount: "900.50", currency: "EUR" })).toBe(`900,5${NBSP}€`);
    expect(formatMoney({ amount: "20000", currency: "TRY" })).toBe(`20.000${NBSP}TL`);
  });

  it("can add a per-unit suffix", () => {
    expect(formatMoney({ amount: "120", currency: "USD" }, "kWp")).toBe(`120${NBSP}$/kWp`);
  });
});

describe("formatRate", () => {
  it("shows an exchange rate with up to four decimals", () => {
    expect(formatRate("50.6286")).toBe("50,6286");
    expect(formatRate("50.6")).toBe("50,60");
  });
});

describe("formatSite", () => {
  it("prefers the address the Sales Rep typed", () => {
    expect(formatSite({ address: "Muratpaşa, Antalya", latitude: null, longitude: null })).toBe(
      "Muratpaşa, Antalya",
    );
  });

  it("falls back to coordinates with their hemispheres", () => {
    expect(formatSite({ address: null, latitude: 39.9031, longitude: 32.8597 })).toBe(
      `39,9031° K, 32,8597° D`,
    );
    expect(formatSite({ address: null, latitude: -1.5, longitude: -2 })).toBe(`1,5° G, 2° B`);
  });
});

describe("MONTH_LABELS", () => {
  it("has the twelve short Turkish month names", () => {
    expect(MONTH_LABELS).toHaveLength(12);
    expect(MONTH_LABELS[0]).toBe("Oca");
    expect(MONTH_LABELS[11]).toBe("Ara");
  });
});
