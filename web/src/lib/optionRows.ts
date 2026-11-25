import type { SystemOptionResponse } from "@/api/types";

import {
  formatCapacityKwp,
  formatKwh,
  formatPaybackYears,
  formatShare,
  formatTry,
} from "./format";

/**
 * The rows that describe a System Option, in one place: the option card and the comparison
 * table both read them, so a figure added here (Netted Share, NPV, IRR: ticket #50) shows up
 * in both with one entry. Every value is the API's own figure, only formatted.
 */

export type OptionContext = { vatRate: string; lifetimeYears: number };

export type OptionRow = {
  id: string;
  label: string | ((context: OptionContext) => string);
  value: (option: SystemOptionResponse, context: OptionContext) => string;
};

const NBSP = "\u00a0";
const kwFormat = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 });

export function rowLabel(row: OptionRow, context: OptionContext): string {
  return typeof row.label === "function" ? row.label(context) : row.label;
}

export const STRATEGY_LABELS: Record<SystemOptionResponse["strategy"], string> = {
  consumption_matched: "Tüketime göre",
  roof_max: "Çatı azami",
};

export const BINDING_LIMIT_LABELS: Record<SystemOptionResponse["binding_limit"], string> = {
  roof: "Çatı alanı",
  consumption_target: "Tüketim hedefi",
  contracted_power: "Sözleşme gücü",
};

export function paybackText(option: SystemOptionResponse, lifetimeYears: number): string {
  const years = option.savings.payback_period_years;
  if (option.savings.payback_beyond_lifetime || years === null || years === undefined) {
    return `${lifetimeYears} yıl içinde geri ödenmiyor`;
  }
  return formatPaybackYears(years);
}

function panelText(option: SystemOptionResponse): string {
  const { manufacturer, model } = option.panel;
  return `${option.panel_count}${NBSP}adet · ${manufacturer} ${model}`;
}

function inverterText(option: SystemOptionResponse): string {
  const { manufacturer, model, ac_power_kw: acPowerKw } = option.inverter;
  return `${manufacturer} ${model} (${kwFormat.format(acPowerKw)}${NBSP}kW)`;
}

const capacity: OptionRow = {
  id: "capacity",
  label: "Sistem gücü",
  value: (option) => formatCapacityKwp(option.capacity_kwp),
};
const panel: OptionRow = { id: "panel", label: "Panel", value: panelText };
const inverter: OptionRow = { id: "inverter", label: "Evirici", value: inverterText };
const production: OptionRow = {
  id: "production",
  label: "Yıllık üretim",
  value: (option) => formatKwh(option.annual_production_kwh),
};
const firstYearSavings: OptionRow = {
  id: "first-year-savings",
  label: "İlk yıl tasarruf",
  value: (option) => formatTry(option.savings.first_year_annual_savings_try),
};

/** The details under the headline figures of an option card. */
export const CARD_ROWS: OptionRow[] = [capacity, panel, inverter, production, firstYearSavings];

/** The comparison table (Tablo 1). `total` and `payback` are styled as the key rows. */
export const COMPARISON_ROWS: (OptionRow & { emphasis?: boolean })[] = [
  { id: "strategy", label: "Strateji", value: (option) => STRATEGY_LABELS[option.strategy] },
  capacity,
  panel,
  inverter,
  {
    id: "binding-limit",
    label: "Sınırlayıcı",
    value: (option) => BINDING_LIMIT_LABELS[option.binding_limit],
  },
  production,
  {
    id: "sale-price",
    label: "Satış bedeli (KDV hariç)",
    value: (option) => formatTry(option.price.sale_price_try),
  },
  {
    id: "vat",
    label: (context) => `KDV (${formatShare(context.vatRate)})`,
    value: (option) => formatTry(option.price.vat_try),
  },
  {
    id: "total",
    label: "Toplam (KDV dahil)",
    value: (option) => formatTry(option.price.total_try),
    emphasis: true,
  },
  firstYearSavings,
  {
    id: "payback",
    label: "Geri ödeme süresi",
    value: (option, context) => paybackText(option, context.lifetimeYears),
  },
];

