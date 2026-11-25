import type { CreateQuoteFailure } from "@/api/create-quote";
import { type FieldError, PROBLEM_TYPES } from "@/api/problem";
import type { Schemas } from "@/api/types";

import { formatWait } from "./format";

/**
 * The New Quote form's rules: what it validates (the API's bounds, in Turkish), the request it
 * builds, and how an API failure becomes messages on fields. No React here, so it can be read
 * on its own; `QuoteForm.test.tsx` drives it through the rendered form.
 */

export type QuoteRequestBody = Schemas["QuoteRequestBody"];

export type SiteMode = "address" | "coordinates";
export type RoofType = "pitched" | "flat";
export type ConsumptionMode = "kwh" | "bill";

/** Everything the Sales Rep types, as text, exactly as typed. */
export interface QuoteFormValues {
  customerName: string;
  phone: string;
  email: string;
  siteMode: SiteMode;
  address: string;
  latitude: string;
  longitude: string;
  roofType: RoofType;
  azimuthDeg: string;
  tiltDeg: string;
  usableAreaM2: string;
  consumptionMode: ConsumptionMode;
  monthlyConsumptionKwh: string;
  monthlyBillTry: string;
  subscriberGroup: string;
  contractedPowerKw: string;
}

export const INITIAL_VALUES: QuoteFormValues = {
  customerName: "",
  phone: "",
  email: "",
  siteMode: "address",
  address: "",
  latitude: "",
  longitude: "",
  roofType: "pitched",
  azimuthDeg: "",
  tiltDeg: "",
  usableAreaM2: "",
  consumptionMode: "kwh",
  monthlyConsumptionKwh: "",
  monthlyBillTry: "",
  subscriberGroup: "residential",
  contractedPowerKw: "",
};

/** A field's DOM id; also the name the API's own field uses, where there is one. */
export type FieldId =
  | "customer_name"
  | "phone"
  | "email"
  | "address"
  | "latitude"
  | "longitude"
  | "azimuth_deg"
  | "tilt_deg"
  | "usable_area_m2"
  | "monthly_consumption_kwh"
  | "monthly_bill_try"
  | "subscriber_group"
  | "contracted_power_kw";

export type FieldErrors = Partial<Record<FieldId, string>>;

/** The order the fields appear on the page: the summary lists errors in it, focus goes to the first. */
export const FIELD_ORDER: readonly FieldId[] = [
  "customer_name",
  "phone",
  "email",
  "address",
  "latitude",
  "longitude",
  "azimuth_deg",
  "tilt_deg",
  "usable_area_m2",
  "monthly_consumption_kwh",
  "monthly_bill_try",
  "subscriber_group",
  "contracted_power_kw",
];

/** How a field is named in a message the API (not the form) caused. */
const FIELD_NAMES: Record<FieldId, string> = {
  customer_name: "Müşteri adı",
  phone: "Telefon",
  email: "E-posta adresi",
  address: "Adres",
  latitude: "Enlem",
  longitude: "Boylam",
  azimuth_deg: "Yön",
  tilt_deg: "Eğim",
  usable_area_m2: "Kullanılabilir alan",
  monthly_consumption_kwh: "Aylık tüketim",
  monthly_bill_try: "Aylık fatura",
  subscriber_group: "Abone grubu",
  contracted_power_kw: "Sözleşme gücü",
};

// The API's bounds (src/sunquote/api/schemas.py). Keep them in step with it.
const NAME_MAX_LENGTH = 200;
const PHONE_MAX_LENGTH = 40;
const LATITUDE_RANGE = { min: -90, max: 90 };
const LONGITUDE_RANGE = { min: -180, max: 180 };
const AZIMUTH_RANGE = { min: 0, maxExclusive: 360 };
const TILT_RANGE = { min: 0, max: 90 };

const EMAIL_INVALID = "E-posta adresi geçerli değil.";
const NOT_A_NUMBER = "Sayı yazın; ondalık için virgül kullanın.";

/**
 * A typed number as the decimal string the API takes (`"39,9031"` becomes `"39.9031"`), or null
 * when it is not a plain number. A dot is read as a decimal point, so thousands separators are
 * not accepted: `2.400` is 2,4.
 */
export function parseDecimal(text: string): string | null {
  const trimmed = text.trim();
  if (!/^[+-]?\d+(?:[.,]\d+)?$/.test(trimmed)) {
    return null;
  }
  return trimmed.replace(",", ".").replace(/^\+/, "");
}

type NumberCheck = (value: number) => string | null;

function checkNumber(text: string, missing: string, check: NumberCheck): string | null {
  if (text.trim() === "") {
    return missing;
  }
  const decimal = parseDecimal(text);
  return decimal === null ? NOT_A_NUMBER : check(Number(decimal));
}

const positive = (message: string): NumberCheck => (value) => (value > 0 ? null : message);

function inRange(message: string, min: number, max: number, maxExclusive = false): NumberCheck {
  return (value) => (value >= min && (maxExclusive ? value < max : value <= max) ? null : message);
}

/** The fields that do not pass, with a Turkish message each. Empty when the form may be sent. */
export function validateQuoteForm(values: QuoteFormValues): FieldErrors {
  const errors: FieldErrors = {};
  const fail = (id: FieldId, message: string | null) => {
    if (message !== null) {
      errors[id] = message;
    }
  };

  const name = values.customerName.trim();
  fail(
    "customer_name",
    name === ""
      ? "Müşteri adı gerekli."
      : name.length > NAME_MAX_LENGTH
        ? `Müşteri adı en fazla ${NAME_MAX_LENGTH} karakter olabilir.`
        : null,
  );
  fail(
    "phone",
    values.phone.trim().length > PHONE_MAX_LENGTH
      ? `Telefon en fazla ${PHONE_MAX_LENGTH} karakter olabilir.`
      : null,
  );
  const email = values.email.trim();
  fail("email", email !== "" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) ? EMAIL_INVALID : null);

  if (values.siteMode === "address") {
    fail(
      "address",
      values.address.trim() === "" ? "Adres gerekli. Bulunamazsa koordinat girebilirsiniz." : null,
    );
  } else {
    fail(
      "latitude",
      checkNumber(
        values.latitude,
        "Enlem gerekli.",
        inRange("Enlem −90 ile 90 arasında olmalı.", LATITUDE_RANGE.min, LATITUDE_RANGE.max),
      ),
    );
    fail(
      "longitude",
      checkNumber(
        values.longitude,
        "Boylam gerekli.",
        inRange("Boylam −180 ile 180 arasında olmalı.", LONGITUDE_RANGE.min, LONGITUDE_RANGE.max),
      ),
    );
  }

  if (values.roofType === "pitched") {
    fail(
      "azimuth_deg",
      checkNumber(
        values.azimuthDeg,
        "Yön gerekli.",
        inRange(
          "Yön 0 ile 360 derece arasında olmalı (360 hariç; 180 = güney).",
          AZIMUTH_RANGE.min,
          AZIMUTH_RANGE.maxExclusive,
          true,
        ),
      ),
    );
    fail(
      "tilt_deg",
      checkNumber(
        values.tiltDeg,
        "Eğim gerekli.",
        inRange("Eğim 0 ile 90 derece arasında olmalı.", TILT_RANGE.min, TILT_RANGE.max),
      ),
    );
  }
  fail(
    "usable_area_m2",
    checkNumber(
      values.usableAreaM2,
      "Kullanılabilir alan gerekli.",
      positive("Kullanılabilir alan 0’dan büyük olmalı."),
    ),
  );

  if (values.consumptionMode === "kwh") {
    fail(
      "monthly_consumption_kwh",
      checkNumber(
        values.monthlyConsumptionKwh,
        "Aylık tüketim gerekli.",
        positive("Aylık tüketim 0’dan büyük olmalı."),
      ),
    );
  } else {
    fail(
      "monthly_bill_try",
      checkNumber(
        values.monthlyBillTry,
        "Aylık fatura gerekli.",
        positive("Aylık fatura 0’dan büyük olmalı."),
      ),
    );
  }

  if (values.contractedPowerKw.trim() !== "") {
    fail(
      "contracted_power_kw",
      checkNumber(
        values.contractedPowerKw,
        "",
        positive("Sözleşme gücü 0’dan büyük olmalı."),
      ),
    );
  }
  return errors;
}

/** The request for a form that passed `validateQuoteForm`. Optional fields left empty are left out. */
export function toQuoteRequest(values: QuoteFormValues): QuoteRequestBody {
  const decimal = (text: string): string => parseDecimal(text) ?? text.trim();
  const optional = (text: string): string | undefined => text.trim() || undefined;

  const phone = optional(values.phone);
  const email = optional(values.email);
  const site: QuoteRequestBody["site"] =
    values.siteMode === "address"
      ? { address: values.address.trim() }
      : { latitude: decimal(values.latitude), longitude: decimal(values.longitude) };
  const roof: QuoteRequestBody["roof"] =
    values.roofType === "pitched"
      ? {
          roof_type: "pitched",
          usable_area_m2: decimal(values.usableAreaM2),
          azimuth_deg: decimal(values.azimuthDeg),
          tilt_deg: decimal(values.tiltDeg),
        }
      : { roof_type: "flat", usable_area_m2: decimal(values.usableAreaM2) };
  const request: QuoteRequestBody = {
    customer: {
      name: values.customerName.trim(),
      ...(phone ? { phone } : {}),
      ...(email ? { email } : {}),
    },
    site,
    roof,
    consumption:
      values.consumptionMode === "kwh"
        ? { monthly_consumption_kwh: decimal(values.monthlyConsumptionKwh) }
        : { monthly_bill_try: decimal(values.monthlyBillTry) },
    subscriber_group: values.subscriberGroup,
  };
  if (values.contractedPowerKw.trim() !== "") {
    request.contracted_power_kw = decimal(values.contractedPowerKw);
  }
  return request;
}

/** The API's field paths, as the form's fields. */
const API_FIELDS: Record<string, FieldId> = {
  "customer.name": "customer_name",
  "customer.phone": "phone",
  "customer.email": "email",
  "site.address": "address",
  "site.latitude": "latitude",
  "site.longitude": "longitude",
  "roof.azimuth_deg": "azimuth_deg",
  "roof.tilt_deg": "tilt_deg",
  "roof.usable_area_m2": "usable_area_m2",
  "consumption.monthly_consumption_kwh": "monthly_consumption_kwh",
  "consumption.monthly_bill_try": "monthly_bill_try",
  subscriber_group: "subscriber_group",
  contracted_power_kw: "contracted_power_kw",
};

/** What a failed submit shows: messages on fields, and a message for the form as a whole. */
export interface SubmitFailureView {
  fieldErrors: FieldErrors;
  /** Null when the field messages say it all. */
  message: string | null;
}

function fieldMessage(id: FieldId): string {
  return id === "email" ? EMAIL_INVALID : `${FIELD_NAMES[id]} geçerli değil.`;
}

/**
 * Turkish messages for a failed submit. The API's own `detail` is English and meant for
 * developers, so it is never shown; each problem type has its own message here.
 */
export function describeFailure(failure: CreateQuoteFailure): SubmitFailureView {
  if (failure.kind === "unavailable") {
    return {
      fieldErrors: {},
      message: "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.",
    };
  }
  if (failure.kind === "unexpected") {
    return { fieldErrors: {}, message: "Beklenmeyen bir hata oluştu. Yeniden deneyin." };
  }

  const { problem } = failure;
  switch (problem.type) {
    case PROBLEM_TYPES.validation:
      return describeValidationProblem(problem.errors);
    case PROBLEM_TYPES.addressNotFound:
      return {
        fieldErrors: { address: "Adres bulunamadı. Adresi kontrol edin veya koordinat girin." },
        message: null,
      };
    case PROBLEM_TYPES.unsupportedSubscriberGroup:
      return {
        fieldErrors: {
          subscriber_group: "Bu abone grubu desteklenmiyor; şimdilik yalnızca mesken seçilebilir.",
        },
        message: null,
      };
    case PROBLEM_TYPES.noViableSystem:
      return {
        fieldErrors: {},
        message:
          "Bu çatı ve tüketim için uygun bir sistem çıkmadı. Kullanılabilir alanı ve tüketimi gözden geçirin.",
      };
    case PROBLEM_TYPES.noCompatibleInverter:
      return {
        fieldErrors: {},
        message:
          "Hesaplanan sistem için uyumlu inverter bulunamadı. Kullanılabilir alanı veya sözleşme gücünü değiştirip yeniden deneyin.",
      };
    case PROBLEM_TYPES.locationNotSupported:
      return {
        fieldErrors: {},
        message:
          "Bu konum desteklenmiyor; şimdilik yalnızca Türkiye’deki konumlar için teklif hazırlanır.",
      };
    case PROBLEM_TYPES.upstreamUnavailable:
      return {
        fieldErrors: {},
        message:
          "Teklif için gereken dış servislere şu an ulaşılamıyor (kur, güneşlenme verisi ya da adres arama). Birkaç dakika sonra yeniden deneyin.",
      };
    case PROBLEM_TYPES.rateLimited:
      return {
        fieldErrors: {},
        message:
          problem.retryAfterSeconds === null
            ? "Çok fazla teklif oluşturdunuz. Bir süre bekleyip yeniden deneyin."
            : `Çok fazla teklif oluşturdunuz. ${formatWait(problem.retryAfterSeconds)} sonra yeniden deneyin.`,
      };
    default:
      return { fieldErrors: {}, message: "Beklenmeyen bir hata oluştu. Yeniden deneyin." };
  }
}

function describeValidationProblem(errors: FieldError[]): SubmitFailureView {
  const fieldErrors: FieldErrors = {};
  let unmapped = false;
  for (const error of errors) {
    const id = API_FIELDS[error.field];
    if (id === undefined) {
      unmapped = true;
    } else {
      fieldErrors[id] = fieldMessage(id);
    }
  }
  const nothingMapped = Object.keys(fieldErrors).length === 0;
  return {
    fieldErrors,
    message:
      unmapped || nothingMapped
        ? "Form gönderilemedi: sunucu girdilerden birini kabul etmedi. Girdileri gözden geçirin."
        : null,
  };
}

/** The error entries in page order. */
export function orderedErrors(errors: FieldErrors): { id: FieldId; message: string }[] {
  return FIELD_ORDER.flatMap((id) => {
    const message = errors[id];
    return message === undefined ? [] : [{ id, message }];
  });
}
