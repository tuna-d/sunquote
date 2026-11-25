import { describe, expect, it } from "vitest";

import { option, secondOption } from "../../test/quoteFixture";
import {
  cumulativeSavingsChart,
  formatAxisTry,
  monthlyProductionRows,
} from "./charts";

describe("monthlyProductionRows", () => {
  it("makes one row per month with one column per System Option", () => {
    const rows = monthlyProductionRows([option(), secondOption()]);

    expect(rows).toHaveLength(12);
    expect(rows[0]).toEqual({ month: "Oca", fullMonth: "Ocak", values: [601, 944] });
    expect(rows[6]).toEqual({ month: "Tem", fullMonth: "Temmuz", values: [1029, 1616] });
  });

  it("has a single column for a one-option Quote", () => {
    const rows = monthlyProductionRows([option()]);
    expect(rows.every((row) => row.values.length === 1)).toBe(true);
  });

  it("orders months by their number whatever order the API lists them in", () => {
    const shuffled = option();
    shuffled.monthly_production_kwh = [...shuffled.monthly_production_kwh].reverse();
    expect(monthlyProductionRows([shuffled]).map((row) => row.month)[0]).toBe("Oca");
  });
});

describe("cumulativeSavingsChart", () => {
  it("starts at year zero with nothing saved, then follows the API's cash flow", () => {
    const chart = cumulativeSavingsChart(option());

    expect(chart.points[0]).toEqual({ year: 0, cumulativeNetSavingsTry: 0 });
    expect(chart.points[1]).toEqual({ year: 1, cumulativeNetSavingsTry: 42962 });
    expect(chart.points).toHaveLength(26);
    expect(chart.points.at(-1)).toEqual({ year: 25, cumulativeNetSavingsTry: 42962 * 25 });
  });

  it("draws the total price as a line and marks the payback on it", () => {
    const chart = cumulativeSavingsChart(option());

    expect(chart.totalPriceTry).toBe(264655);
    expect(chart.payback).toEqual({ year: 5.9, valueTry: 264655 });
  });

  it("has no payback marker when the price is not recovered within the lifetime", () => {
    const never = option();
    never.savings = { ...never.savings, payback_period_years: null, payback_beyond_lifetime: true };

    expect(cumulativeSavingsChart(never).payback).toBeNull();
  });

  it("reaches to the last year of the cash flow", () => {
    expect(cumulativeSavingsChart(option()).lastYear).toBe(25);
  });
});

describe("formatAxisTry", () => {
  it("shortens lira amounts the way a printed report does", () => {
    expect(formatAxisTry(0)).toBe("0");
    expect(formatAxisTry(200000)).toBe("200\xa0bin");
    expect(formatAxisTry(1000000)).toBe("1\xa0mn");
    expect(formatAxisTry(1300000)).toBe("1,3\xa0mn");
  });
});
