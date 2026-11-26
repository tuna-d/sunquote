import type { AssumptionsResponse, QuoteResponse, SystemOptionResponse } from "@/api/types";

/** Real-shaped API data for the detail page tests (a trimmed Antalya sample Quote). */
const MONTHLY_1 = [601, 657, 864, 919, 963, 968, 1029, 1021, 942, 827, 692, 604];

/** 25 years of cumulative net savings for a system priced at `price`: a straight line. */
function cashFlow(perYear: number) {
  return Array.from({ length: 25 }, (_, index) => ({
    year: index + 1,
    production_kwh: 10000,
    netted_kwh: 9300,
    exported_kwh: 700,
    netting_savings_try: perYear - 1000,
    export_income_try: 1000,
    annual_savings_try: perYear,
    inverter_replacement_try: 0,
    net_savings_try: perYear,
    cumulative_net_savings_try: perYear * (index + 1),
  }));
}

export function option(overrides: Partial<SystemOptionResponse> = {}): SystemOptionResponse {
  return {
    strategy: "consumption_matched",
    panel: {
      panel_id: "trina-vertex-s-plus-neg9rh25-440",
      manufacturer: "Trina Solar",
      model: "Vertex S+ TSM-NEG9RH.25 (440 W)",
      power_w: 440,
    },
    panel_count: 14,
    capacity_kwp: 6.16,
    binding_limit: "consumption_target",
    annual_production_kwh: 10087,
    monthly_production_kwh: MONTHLY_1.map((production_kwh, index) => ({
      month: index + 1,
      production_kwh,
    })),
    netted_share: 0.925,
    inverter: {
      inverter_id: "huawei-sun2000-5ktl-m1",
      manufacturer: "Huawei",
      model: "SUN2000-5KTL-M1",
      ac_power_kw: 5,
    },
    price: {
      installation_cost_try: 176436,
      sale_price_try: 220545,
      vat_try: 44109,
      total_try: 264655,
    },
    savings: {
      first_year_annual_savings_try: 42962,
      payback_period_years: 5.9,
      payback_beyond_lifetime: false,
      npv_try: 384984,
      irr: 0.171,
      lifetime_savings_try: 1283963,
      cash_flow: cashFlow(42962),
    },
    ...overrides,
  };
}

export function secondOption(): SystemOptionResponse {
  return option({
    strategy: "roof_max",
    panel_count: 22,
    capacity_kwp: 9.68,
    binding_limit: "roof",
    annual_production_kwh: 15851,
    netted_share: 0.64,
    monthly_production_kwh: MONTHLY_1.map((production_kwh, index) => ({
      month: index + 1,
      production_kwh: Math.round(production_kwh * 1.57),
    })),
    inverter: {
      inverter_id: "huawei-sun2000-8ktl-m1",
      manufacturer: "Huawei",
      model: "SUN2000-8KTL-M1",
      ac_power_kw: 8,
    },
    price: {
      installation_cost_try: 306410,
      sale_price_try: 383012,
      vat_try: 76602,
      total_try: 459614,
    },
    savings: {
      first_year_annual_savings_try: 60500,
      payback_period_years: 7.6,
      payback_beyond_lifetime: false,
      npv_try: 520000,
      irr: 0.15,
      lifetime_savings_try: 1500000,
      cash_flow: cashFlow(60500),
    },
  });
}

export function assumptions(overrides: Partial<AssumptionsResponse> = {}): AssumptionsResponse {
  return {
    submitted_request: {
      customer: { name: "Demo Antalya A", phone: null, email: null },
      site: { latitude: null, longitude: null, address: "Muratpaşa, Antalya" },
      roof: { roof_type: "pitched", usable_area_m2: 55, azimuth_deg: 200, tilt_deg: 35 },
      consumption: { monthly_consumption_kwh: 850, monthly_bill_try: null },
      subscriber_group: "residential",
      contracted_power_kw: null,
    },
    geocoding_result: {
      display_name: "Antalya, Muratpaşa, Antalya, Akdeniz Bölgesi, 07050, Türkiye",
      latitude: 36.8865728,
      longitude: 30.7030242,
    },
    pvgis_inputs: {
      source: "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc",
      latitude: 36.887,
      longitude: 30.703,
      tilt_deg: 35,
      aspect_deg: 20,
      system_loss_percent: 14,
    },
    roof_type: "pitched",
    effective_azimuth_deg: 200,
    effective_tilt_deg: 35,
    coverage_ratio: "0.80",
    default_panel: {
      panel_id: "trina-vertex-s-plus-neg9rh25-440",
      manufacturer: "Trina Solar",
      model: "Vertex S+ TSM-NEG9RH.25 (440 W)",
      power_w: 440,
      length_mm: 1762,
      width_mm: 1134,
      area_m2: 1.998108,
      degradation_rate_per_year: "0.0047",
      unit_price: { amount: "76", currency: "USD" },
    },
    inverters: [
      {
        inverter_id: "huawei-sun2000-5ktl-m1",
        manufacturer: "Huawei",
        model: "SUN2000-5KTL-M1",
        ac_power_kw: 5,
        unit_price: { amount: "900", currency: "USD" },
      },
    ],
    dc_ac_ratio_range: { minimum: "1.00", maximum: "1.50" },
    contracted_power: { kw: 10, source: "defaulted" },
    pricing: {
      bos_price_per_kwp: { amount: "120", currency: "USD" },
      labour_price_per_kwp: { amount: "4000", currency: "TRY" },
      fixed_project_cost: { amount: "20000", currency: "TRY" },
      margin: "0.25",
      vat_rate: "0.20",
      validity_period_days: 15,
    },
    exchange_rate: {
      base_currency: "USD",
      quote_currency: "TRY",
      rate: "50.6286",
      date: "2026-11-24",
      overridden: false,
    },
    consumption_derived_from_bill: false,
    derived_monthly_consumption_kwh: null,
    annual_consumption_kwh: 10200,
    low_tier_consumption_kwh: 2920,
    high_tier_consumption_kwh: 7280,
    tariff: {
      tier_threshold_kwh_per_day: "8",
      low_tariff_try_per_kwh: "3.24",
      high_tariff_try_per_kwh: "4.86",
      export_price_try_per_kwh: "1.24",
      valid_from: "2026-04-04",
      source: "EPDK electricity tariff table valid from 2026-04-04",
    },
    financial: {
      tariff_escalation_rate_real: "0.02",
      equipment_escalation_rate_real: "0",
      lifetime_years: 25,
      inverter_replacement_year: 12,
      discount_rate_real: "0.056",
    },
    ...overrides,
  };
}

/** A stored Quote with one System Option, or two with `options: 2`. */
export function quote(
  overrides: Partial<QuoteResponse> & { options?: 1 | 2 } = {},
): QuoteResponse {
  const { options = 2, ...rest } = overrides;
  const systemOptions = options === 2 ? [option(), secondOption()] : [option()];
  return {
    id: "cb63fd31-c8cc-4b4f-a0d3-f712d770c106",
    quote_number: "SQ-2026-000005",
    created_at: "2026-11-25T13:02:27.629225Z",
    is_sample: true,
    customer: { name: "Demo Antalya A", phone: null, email: null },
    quote_date: "2026-11-25",
    valid_until: "2026-12-10",
    narrative: {
      greeting: "Sayın Demo Antalya A,",
      summary:
        "Çatınız ve elektrik tüketiminiz için hazırladığımız teklif aşağıdadır. İlk seçenek 6,16 kWp gücünde bir sistemdir.",
      options_comparison: options === 2 ? "İki seçenek boyut ve fiyat bakımından farklıdır." : null,
      next_steps: "Teklifteki fiyatlar 10.12.2026 tarihine kadar geçerlidir.",
      source: "fallback",
      model: null,
      fallback_reason: null,
      generated_at: "2026-11-25T13:02:27.626478Z",
    },
    assumptions: assumptions(),
    system_options: systemOptions,
    ...rest,
  };
}
