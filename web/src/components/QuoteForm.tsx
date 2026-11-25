"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";

import { type ApiClient, createApiClient } from "@/api/client";
import { createQuote } from "@/api/create-quote";
import {
  describeFailure,
  type FieldErrors,
  type FieldId,
  INITIAL_VALUES,
  orderedErrors,
  type QuoteFormValues,
  toQuoteRequest,
  validateQuoteForm,
} from "@/lib/quote-form";

import { CompassPicker } from "./CompassPicker";
import { DemoBanner } from "./demo-banner";
import styles from "./QuoteForm.module.css";

/** The New Quote form. It sends `POST /quotes` and, on success, opens the Quote's page. */
export function QuoteForm({ client }: { client?: ApiClient }) {
  const router = useRouter();
  const [values, setValues] = useState<QuoteFormValues>(INITIAL_VALUES);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Bumped whenever a failure should move focus: to the first invalid field, or to the message.
  const [focusRequest, setFocusRequest] = useState(0);
  const alertRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (focusRequest === 0) {
      return;
    }
    const first = orderedErrors(errors)[0];
    const target = first ? document.getElementById(first.id) : alertRef.current;
    target?.focus();
    // Only a new failure moves focus; editing a field must not.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusRequest]);

  const set = <K extends keyof QuoteFormValues>(key: K, value: QuoteFormValues[K]) =>
    setValues((current) => ({ ...current, [key]: value }));

  const clearError = (id: FieldId) =>
    setErrors((current) => {
      if (current[id] === undefined) {
        return current;
      }
      const rest = { ...current };
      delete rest[id];
      return rest;
    });

  const fail = (fieldErrors: FieldErrors, formMessage: string | null) => {
    setErrors(fieldErrors);
    setMessage(formMessage);
    setSubmitting(false);
    setFocusRequest((count) => count + 1);
  };

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    const invalid = validateQuoteForm(values);
    if (Object.keys(invalid).length > 0) {
      fail(invalid, null);
      return;
    }
    setSubmitting(true);
    setErrors({});
    setMessage(null);
    const result = await createQuote(toQuoteRequest(values), client ?? createApiClient());
    if (result.ok) {
      // Stay "submitting" while the browser navigates, so the Quote cannot be sent twice.
      router.push(`/quotes/${result.id}`);
      return;
    }
    const failure = describeFailure(result);
    fail(failure.fieldErrors, failure.message);
  }

  /** Props every text field shares: its value, its change handler and its error wiring. */
  const field = (id: FieldId, key: keyof QuoteFormValues, describedBy?: string) => ({
    id,
    value: values[key],
    onChange: (value: string) => {
      set(key, value as never);
      clearError(id);
    },
    error: errors[id],
    describedBy,
  });

  const listed = orderedErrors(errors);

  return (
    <form className={styles.form} noValidate onSubmit={onSubmit}>
      <header>
        <p className="kick">Yeni teklif</p>
        <h1>Teklif talep formu</h1>
        <p className="sub">
          Müşteriyi, yeri ve çatıyı yazın; sistem seçeneklerini hesaplayalım.
        </p>
      </header>
      <DemoBanner />

      {listed.length > 0 || message !== null ? (
        <div className={styles.errsum} role="alert" tabIndex={-1} ref={alertRef}>
          {listed.length > 0 ? (
            <>
              <p>{listed.length} alanı düzeltin:</p>
              <ul>
                {listed.map((item) => (
                  <li key={item.id}>
                    <a href={`#${item.id}`} onClick={focusField(item.id)}>
                      {item.message}
                    </a>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {message !== null ? <p>{message}</p> : null}
        </div>
      ) : null}

      <Section number="01" title="Müşteri" titleId="g-customer">
        <TextField {...field("customer_name", "customerName")} label="Müşteri adı" required />
        <TextField {...field("phone", "phone")} label="Telefon" optional type="tel" />
        <TextField {...field("email", "email")} label="E-posta" optional type="email" />
      </Section>

      <Section number="02" title="Yer" titleId="g-site">
        <Choice
          legend="Konum nasıl verilecek?"
          name="site_mode"
          value={values.siteMode}
          onChange={(value) => set("siteMode", value)}
          options={[
            { value: "address", label: "Adres" },
            { value: "coordinates", label: "Koordinat" },
          ]}
        />
        {values.siteMode === "address" ? (
          <TextField
            {...field("address", "address")}
            label="Adres"
            hint="ilçe, il"
            required
            wide
          />
        ) : (
          <div className={styles.pair}>
            <TextField
              {...field("latitude", "latitude")}
              label="Enlem"
              required
              inputMode="decimal"
              placeholder="39,9031"
            />
            <TextField
              {...field("longitude", "longitude")}
              label="Boylam"
              required
              inputMode="decimal"
              placeholder="32,8597"
            />
          </div>
        )}
      </Section>

      <Section number="03" title="Çatı" titleId="g-roof">
        <Choice
          legend="Çatı tipi"
          name="roof_type"
          value={values.roofType}
          onChange={(value) => set("roofType", value)}
          options={[
            { value: "pitched", label: "Eğimli" },
            { value: "flat", label: "Düz" },
          ]}
        />
        {values.roofType === "pitched" ? (
          <>
            <CompassPicker {...field("azimuth_deg", "azimuthDeg")} />
            <TextField
              {...field("tilt_deg", "tiltDeg")}
              label="Eğim"
              hint="0° yatay, 90° dikey"
              required
              unit="derece"
              short
            />
          </>
        ) : (
          <p className={styles.hint}>
            Düz çatıda paneller güneye bakan sabit eğimli taşıyıcılara kurulur; yön ve eğim sorulmaz.
          </p>
        )}
        <TextField
          {...field("usable_area_m2", "usableAreaM2")}
          label="Kullanılabilir alan"
          hint="baca, pencere vb. hariç"
          required
          unit="m²"
          short
        />
      </Section>

      <Section number="04" title="Tüketim" titleId="g-consumption">
        <Choice
          legend="Müşteri hangisini biliyor?"
          name="consumption_mode"
          value={values.consumptionMode}
          onChange={(value) => set("consumptionMode", value)}
          options={[
            { value: "kwh", label: "Aylık kWh" },
            { value: "bill", label: "Aylık fatura" },
          ]}
        />
        {values.consumptionMode === "kwh" ? (
          <TextField
            {...field("monthly_consumption_kwh", "monthlyConsumptionKwh")}
            label="Aylık tüketim"
            required
            unit="kWh / ay"
            short
          />
        ) : (
          <TextField
            {...field("monthly_bill_try", "monthlyBillTry")}
            label="Aylık fatura tutarı"
            hint="vergiler dahil"
            required
            unit="₺ / ay"
            short
            placeholder="2400"
          />
        )}
        <div>
          <label className={styles.fl} htmlFor="subscriber_group">
            Abone grubu
          </label>
          <select
            id="subscriber_group"
            className={styles.input}
            value={values.subscriberGroup}
            onChange={(event) => {
              set("subscriberGroup", event.target.value);
              clearError("subscriber_group");
            }}
            aria-invalid={errors.subscriber_group ? true : undefined}
            aria-describedby={describedBy("subscriber_group", errors, "h-subscriber_group")}
          >
            <option value="residential">Mesken</option>
          </select>
          <p className={styles.hint} id="h-subscriber_group">
            Şimdilik yalnızca mesken desteklenir.
          </p>
          <FieldError id="subscriber_group" message={errors.subscriber_group} />
        </div>
        <TextField
          {...field("contracted_power_kw", "contractedPowerKw", "h-contracted_power_kw")}
          label="Sözleşme gücü"
          optional
          unit="kW"
          short
          footer={
            <p className={styles.hint} id="h-contracted_power_kw">
              Boş bırakılırsa abone grubunun varsayılan değeri kullanılır ve teklifte belirtilir.
            </p>
          }
        />
      </Section>

      <div className={styles.formend}>
        <button className="btn" type="submit" disabled={submitting}>
          {submitting ? "Teklif hazırlanıyor…" : <>Teklifi oluştur <span aria-hidden="true">→</span></>}
        </button>
      </div>
    </form>
  );
}

function focusField(id: FieldId) {
  return (event: { preventDefault: () => void }) => {
    event.preventDefault();
    document.getElementById(id)?.focus();
  };
}

function describedBy(id: FieldId, errors: FieldErrors, hintId?: string): string | undefined {
  const ids = [hintId, errors[id] ? `e-${id}` : undefined].filter(Boolean);
  return ids.length > 0 ? ids.join(" ") : undefined;
}

function FieldError({ id, message }: { id: FieldId; message: string | undefined }) {
  return message ? (
    <p className={styles.err} id={`e-${id}`}>
      {message}
    </p>
  ) : null;
}

function Section({
  number,
  title,
  titleId,
  children,
}: {
  number: string;
  title: string;
  titleId: string;
  children: ReactNode;
}) {
  return (
    <div className={styles.fsec} role="group" aria-labelledby={titleId}>
      <div className={styles.lg} id={titleId}>
        <span className={styles.num}>{number}</span>
        {title}
      </div>
      <div className={styles.fields}>{children}</div>
    </div>
  );
}

/** A segmented choice of two or more: radio inputs styled as a joined control. */
function Choice<V extends string>({
  legend,
  name,
  value,
  onChange,
  options,
}: {
  legend: string;
  name: string;
  value: V;
  onChange: (value: V) => void;
  options: { value: V; label: string }[];
}) {
  const legendId = `l-${name}`;
  return (
    <div>
      <span className={styles.fl} id={legendId}>
        {legend}
      </span>
      <div className={styles.seg} role="radiogroup" aria-labelledby={legendId}>
        {options.map((option) => (
          <label key={option.value}>
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

interface TextFieldProps {
  id: FieldId;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error: string | undefined;
  describedBy?: string | undefined;
  hint?: string;
  required?: boolean;
  optional?: boolean;
  type?: "text" | "tel" | "email";
  inputMode?: "decimal";
  placeholder?: string;
  unit?: string;
  short?: boolean;
  wide?: boolean;
  footer?: ReactNode;
}

function TextField(props: TextFieldProps) {
  const { id, label, value, onChange, error, hint, required, optional, unit, footer } = props;
  const numeric = props.inputMode === "decimal" || props.short === true;
  const input = (
    <input
      id={id}
      className={`${styles.input} ${props.short ? styles.short : ""} ${props.wide ? styles.wide : ""}`}
      type={props.type ?? "text"}
      inputMode={numeric ? "decimal" : undefined}
      autoComplete="off"
      placeholder={props.placeholder}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      aria-invalid={error ? true : undefined}
      aria-describedby={describedBy(id, error ? { [id]: error } : {}, props.describedBy)}
    />
  );
  return (
    <div>
      <label className={styles.fl} htmlFor={id}>
        {label}{" "}
        {required ? (
          <span className={styles.req} aria-hidden="true">
            *
          </span>
        ) : null}
        {optional ? <small>isteğe bağlı</small> : null}
        {hint ? <small>{hint}</small> : null}
      </label>
      {unit ? (
        <div className={styles.unit}>
          {input}
          <span>{unit}</span>
        </div>
      ) : (
        input
      )}
      {footer}
      <FieldError id={id} message={error} />
    </div>
  );
}
