import { describe, expect, it } from "vitest";

import {
  formatCapacityKwp,
  formatCreatedAt,
  formatLocation,
  formatOptionCount,
  formatTry,
  formatWait,
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

describe("formatWait", () => {
  it("rounds a wait up to the unit it reads best in", () => {
    expect(formatWait(1)).toBe("1 saniye");
    expect(formatWait(45)).toBe("45 saniye");
    expect(formatWait(60)).toBe("1 dakika");
    expect(formatWait(61)).toBe("2 dakika");
    expect(formatWait(1800)).toBe("30 dakika");
    expect(formatWait(3599)).toBe("60 dakika");
    expect(formatWait(3600)).toBe("1 saat");
    expect(formatWait(5400)).toBe("2 saat");
  });

  it("treats no wait as a moment", () => {
    expect(formatWait(0)).toBe("1 saniye");
  });
});
