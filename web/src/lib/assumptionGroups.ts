import type { AssumptionsResponse } from "@/api/types";

import {
  formatDate,
  formatKwh,
  formatMoney,
  formatRate,
  formatShare,
  formatTry,
  formatTryPerKwh,
} from "./format";

/**
 * The Assumptions table (Ek A): every value the Quote was calculated with, formatted from what
 * the API recorded. Nothing is computed; the groups follow the mockup.
 */

export type AssumptionItem = { label: string; value: string };
export type AssumptionGroup = { title: string; items: AssumptionItem[]; note?: string };

const NBSP = "\xa0";
const plainNumber = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 });
const twoDecimals = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function pvgisHost(source: string): string {
  try {
    return new URL(source).host;
  } catch {
    return source;
  }
}

export function assumptionGroups(assumptions: AssumptionsResponse): AssumptionGroup[] {
  const { exchange_rate: rate, pricing, tariff, financial, default_panel: panel } = assumptions;
  const submitted = assumptions.submitted_request;
  const power = assumptions.contracted_power;
  const range = assumptions.dc_ac_ratio_range;

  const rateSource = rate.overridden ? "elle girildi" : "TCMB";
  const priceAndRates: AssumptionItem[] = [
    {
      label: "Döviz kuru",
      value: `1${NBSP}${rate.base_currency} = ${formatRate(rate.rate)}${NBSP}TL (${formatDate(rate.date)}, ${rateSource})`,
    },
    {
      label: "Panel",
      value: `${panel.manufacturer} ${panel.model} · birim fiyat ${formatMoney(panel.unit_price)}`,
    },
    ...assumptions.inverters.map((inverter) => ({
      label: "Evirici",
      value: `${inverter.manufacturer} ${inverter.model} (${plainNumber.format(inverter.ac_power_kw)}${NBSP}kW) · ${formatMoney(inverter.unit_price)}`,
    })),
    { label: "Montaj malzemesi", value: formatMoney(pricing.bos_price_per_kwp, "kWp") },
    { label: "İşçilik", value: formatMoney(pricing.labour_price_per_kwp, "kWp") },
    { label: "Sabit proje maliyeti", value: formatMoney(pricing.fixed_project_cost) },
    { label: "Kâr marjı", value: formatShare(pricing.margin) },
    { label: "KDV", value: formatShare(pricing.vat_rate) },
    { label: "Teklif geçerliliği", value: `${pricing.validity_period_days}${NBSP}gün` },
  ];

  const production: AssumptionItem[] = [
    {
      label: "Yön / eğim (etkin)",
      value: `${plainNumber.format(assumptions.effective_azimuth_deg)}° / ${plainNumber.format(assumptions.effective_tilt_deg)}°`,
    },
    { label: "Üretim verisi", value: `PVGIS · ${pvgisHost(assumptions.pvgis_inputs.source)}` },
    { label: "Sistem kaybı", value: `%${plainNumber.format(assumptions.pvgis_inputs.system_loss_percent)}` },
    { label: "Çatı kullanım oranı", value: formatShare(assumptions.coverage_ratio) },
    {
      label: "DC/AC oranı aralığı",
      value: `${twoDecimals.format(Number(range.minimum))} – ${twoDecimals.format(Number(range.maximum))}`,
    },
    {
      label: "Sözleşme gücü",
      value: `${plainNumber.format(power.kw)}${NBSP}kW (${power.source === "given" ? "verilen" : "varsayılan"})`,
    },
    { label: "Panel bozunması", value: `${formatShare(panel.degradation_rate_per_year)}/yıl` },
  ];

  const bill = submitted.consumption.monthly_bill_try;
  const tariffItems: AssumptionItem[] = [
    { label: "Yıllık tüketim", value: formatKwh(assumptions.annual_consumption_kwh) },
    ...(assumptions.consumption_derived_from_bill && bill
      ? [
          {
            label: "Aylık fatura",
            value: `${formatTry(Number(bill))} (tüketim faturadan türetildi)`,
          },
        ]
      : []),
    {
      label: "Kademe sınırı",
      value: `${plainNumber.format(Number(tariff.tier_threshold_kwh_per_day))}${NBSP}kWh/gün`,
    },
    {
      label: "Düşük kademe",
      value: `${formatTryPerKwh(tariff.low_tariff_try_per_kwh)} · ${formatKwh(assumptions.low_tier_consumption_kwh)}`,
    },
    {
      label: "Yüksek kademe",
      value: `${formatTryPerKwh(tariff.high_tariff_try_per_kwh)} · ${formatKwh(assumptions.high_tier_consumption_kwh)}`,
    },
    { label: "İhracat fiyatı", value: formatTryPerKwh(tariff.export_price_try_per_kwh) },
    { label: "Tarife tarihi", value: formatDate(tariff.valid_from) },
  ];

  const financialItems: AssumptionItem[] = [
    { label: "Reel tarife artışı", value: `${formatShare(financial.tariff_escalation_rate_real)}/yıl` },
    {
      label: "Reel ekipman artışı",
      value: `${formatShare(financial.equipment_escalation_rate_real)}/yıl`,
    },
    { label: "İskonto oranı (reel)", value: formatShare(financial.discount_rate_real) },
    { label: "Ömür", value: `${financial.lifetime_years}${NBSP}yıl` },
    { label: "Evirici değişimi", value: `${financial.inverter_replacement_year}. yıl` },
  ];

  return [
    { title: "Kur ve fiyat", items: priceAndRates },
    { title: "Üretim", items: production },
    { title: "Tarife", items: tariffItems, note: `Tarife kaynağı: ${tariff.source}` },
    { title: "Finansal", items: financialItems },
  ];
}

export function assumptionCount(groups: AssumptionGroup[]): number {
  return groups.reduce((total, group) => total + group.items.length, 0);
}
