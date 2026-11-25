import type { SystemOptionResponse } from "@/api/types";

import { MONTH_LABELS, MONTH_NAMES } from "./format";

/**
 * Shapes the API's figures for the charts. Nothing is computed here: rows are reordered and
 * relabelled, and the one added point (year 0) is the chart's origin, not a figure.
 */

export type MonthlyRow = {
  /** Short axis label. */
  month: string;
  /** Full month name, for tooltips and screen readers. */
  fullMonth: string;
  /** The month's production in kWh for each System Option, in option order. */
  values: number[];
};

export function monthlyProductionRows(options: SystemOptionResponse[]): MonthlyRow[] {
  return MONTH_LABELS.map((month, index) => ({
    month,
    fullMonth: MONTH_NAMES[index]!,
    values: options.map((option) => {
      const found = option.monthly_production_kwh.find((row) => row.month === index + 1);
      return found?.production_kwh ?? 0;
    }),
  }));
}

export type CumulativeSavingsChart = {
  /** Year 0 (nothing saved yet) then each year of the API's cash flow. */
  points: { year: number; cumulativeNetSavingsTry: number }[];
  totalPriceTry: number;
  /** Where the cumulative line meets the price: the API's Payback Period; null when never. */
  payback: { year: number; valueTry: number } | null;
  lastYear: number;
};

export function cumulativeSavingsChart(option: SystemOptionResponse): CumulativeSavingsChart {
  const rows = [...option.savings.cash_flow].sort((a, b) => a.year - b.year);
  const totalPriceTry = option.price.total_try;
  const paybackYears = option.savings.payback_period_years;
  return {
    points: [
      { year: 0, cumulativeNetSavingsTry: 0 },
      ...rows.map((row) => ({
        year: row.year,
        cumulativeNetSavingsTry: row.cumulative_net_savings_try,
      })),
    ],
    totalPriceTry,
    payback:
      paybackYears === null || paybackYears === undefined
        ? null
        : { year: paybackYears, valueTry: totalPriceTry },
    lastYear: rows.at(-1)?.year ?? 0,
  };
}

const NBSP = "\xa0";

const axisTryFormat = new Intl.NumberFormat("tr-TR", {
  notation: "compact",
  compactDisplay: "long",
  maximumFractionDigits: 1,
});

/** `200 bin`, `1,2 mn`: an axis tick for a lira amount, short enough to stay on one line. */
export function formatAxisTry(amountTry: number): string {
  return axisTryFormat.format(amountTry).replace(" milyon", " mn").replace(" ", NBSP);
}
