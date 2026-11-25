import Link from "next/link";

import type { QuoteResult } from "@/api/quote";
import type { QuoteResponse } from "@/api/types";
import { assumptionCount, assumptionGroups } from "@/lib/assumptionGroups";
import { cumulativeSavingsChart, monthlyProductionRows } from "@/lib/charts";
import {
  formatDate,
  formatKwh,
  formatPaybackYears,
  formatSite,
  formatTry,
} from "@/lib/format";
import {
  COMPARISON_ROWS,
  type OptionContext,
  paybackText,
  rowLabel,
} from "@/lib/optionRows";

import { CumulativeSavingsChart } from "./CumulativeSavingsChart";
import { OptionCard } from "./OptionCard";
import { ProductionChart } from "./ProductionChart";
import styles from "./QuoteDetailView.module.css";

const NBSP = "\xa0";
const areaFormat = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 });

export type QuoteDetailResult = Exclude<QuoteResult, { ok: false; reason: "not-found" }>;

function documentHref(id: string): string {
  return `/api/quotes/${id}/document`;
}

/**
 * The Quote detail page's content. Pure: no data fetching here. The page sends an unknown id to
 * Next's not-found page (`QuoteNotFound`) and gives this view the Quote or the failure.
 */
export function QuoteDetailView({ result, id }: { result: QuoteDetailResult; id: string }) {
  if (!result.ok) {
    return <Failure reason={result.reason} id={id} />;
  }
  return <Detail quote={result.quote} />;
}

function Detail({ quote }: { quote: QuoteResponse }) {
  const { assumptions, system_options: options } = quote;
  const context: OptionContext = {
    vatRate: assumptions.pricing.vat_rate,
    lifetimeYears: assumptions.financial.lifetime_years,
  };
  const request = assumptions.submitted_request;
  const roofKind = request.roof.roof_type === "pitched" ? "eğimli çatı" : "düz çatı";
  const monthlyConsumption =
    request.consumption.monthly_consumption_kwh ??
    (assumptions.derived_monthly_consumption_kwh === null
      ? null
      : Number(assumptions.derived_monthly_consumption_kwh));
  const single = options.length === 1;

  return (
    <article className="sheet" aria-labelledby="title">
      <header className="letter">
        <div>
          <p className="kick">Güneş enerjisi teklifi</p>
          <h1 id="title">{quote.customer.name}</h1>
          <p className="sub">
            {formatSite(request.site)} · {roofKind}, {areaFormat.format(request.roof.usable_area_m2)}
            {NBSP}m²
          </p>
        </div>
        <dl className="meta">
          <div>
            <dt>Teklif no</dt>
            <dd>{quote.quote_number}</dd>
          </div>
          <div>
            <dt>Tarih</dt>
            <dd>{formatDate(quote.quote_date)}</dd>
          </div>
          <div>
            <dt>Geçerlilik</dt>
            <dd>{formatDate(quote.valid_until)}</dd>
          </div>
          <div>
            <dt>Tüketim</dt>
            <dd>{formatKwh(assumptions.annual_consumption_kwh)}/yıl</dd>
          </div>
        </dl>
      </header>

      <p className="lede">{quote.narrative.summary}</p>
      <p className={styles.actions}>
        <DocumentLink id={quote.id} />
      </p>

      <section className={styles.part} aria-labelledby="s1">
        <header>
          <p className="kick">Bölüm 1</p>
          <h2 id="s1">{single ? "Sistem seçeneği" : "İki seçenek"}</h2>
        </header>
        <div className={`${styles.cards} ${single ? styles.single : ""}`}>
          {options.map((option, index) => (
            <OptionCard
              key={index}
              option={option}
              number={(index + 1) as 1 | 2}
              context={context}
            />
          ))}
        </div>
        <ComparisonTable quote={quote} context={context} />
      </section>

      <section className={styles.part} aria-labelledby="s2">
        <header>
          <p className="kick">Bölüm 2</p>
          <h2 id="s2">Üretim</h2>
        </header>
        <ProductionFigure quote={quote} monthlyConsumption={monthlyConsumption} />
      </section>

      <section className={styles.part} aria-labelledby="s3">
        <header>
          <p className="kick">Bölüm 3</p>
          <h2 id="s3">Geri ödeme</h2>
        </header>
        <PaybackFigures quote={quote} />
      </section>

      <section className={styles.part} aria-labelledby="s4">
        <Assumptions quote={quote} />
      </section>

      <div className={styles.endRow}>
        <p>Teklifin müşteriye verilecek, yazdırılabilir Türkçe belgesi.</p>
        <DocumentLink id={quote.id} ghost />
      </div>
    </article>
  );
}

function DocumentLink({ id, ghost = false }: { id: string; ghost?: boolean }) {
  return (
    <a
      className={ghost ? "btn ghost" : "btn"}
      href={documentHref(id)}
      target="_blank"
      rel="noopener noreferrer"
    >
      Teklif belgesini aç <span aria-hidden="true">→</span>
      <span className="sr"> (yeni sekmede açılır)</span>
    </a>
  );
}

function ComparisonTable({ quote, context }: { quote: QuoteResponse; context: OptionContext }) {
  const options = quote.system_options;
  return (
    <table className={`t ${styles.compare}`}>
      <caption>
        Tablo 1. Sistem seçenekleri. Tutarlar bugünün lirasıyla, tam lira olarak gösterilir.
      </caption>
      <thead>
        <tr>
          <th scope="col">Kalem</th>
          {options.map((_, index) => (
            <th key={index} scope="col">
              Seçenek {index + 1}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {COMPARISON_ROWS.map((row) => (
          <tr key={row.id} className={row.emphasis ? styles.total : undefined}>
            <th scope="row">{rowLabel(row, context)}</th>
            {options.map((option, index) => (
              <td key={index}>{row.value(option, context)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Key({ children, swatch }: { children: React.ReactNode; swatch: string | undefined }) {
  return (
    <span>
      <i className={swatch} aria-hidden="true" />
      {children}
    </span>
  );
}

function ProductionFigure({
  quote,
  monthlyConsumption,
}: {
  quote: QuoteResponse;
  monthlyConsumption: number | null;
}) {
  const options = quote.system_options;
  const rows = monthlyProductionRows(options);
  const peak = rows.reduce((best, row) => (row.values[0]! > best.values[0]! ? row : best), rows[0]!);
  const summary = `Aylık üretim, kWh. ${options
    .map((option, index) => `Seçenek ${index + 1}: yılda ${formatKwh(option.annual_production_kwh)}`)
    .join("; ")}. En yüksek ay ${peak.fullMonth}.`;
  return (
    <figure className={styles.figure}>
      <div className={styles.key}>
        <Key swatch={styles.k1}>Seçenek 1</Key>
        {options.length > 1 ? <Key swatch={styles.k2}>Seçenek 2</Key> : null}
        {monthlyConsumption !== null ? (
          <Key swatch={styles.kc}>Aylık tüketim ({formatKwh(Math.round(monthlyConsumption))})</Key>
        ) : null}
      </div>
      <div role="img" aria-label={summary}>
        <ProductionChart rows={rows} monthlyConsumptionKwh={monthlyConsumption} />
      </div>
      <table className="sr">
        <caption>Aylık üretim, kWh</caption>
        <thead>
          <tr>
            <th scope="col">Ay</th>
            {options.map((_, index) => (
              <th key={index} scope="col">
                Seçenek {index + 1}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.fullMonth}>
              <th scope="row">{row.fullMonth}</th>
              {row.values.map((value, index) => (
                <td key={index}>{formatKwh(value)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <figcaption>
        <b>Şekil 1</b>
        Tahmini aylık üretim, kWh. Kaynak: PVGIS, sistem kaybı %
        {quote.assumptions.pvgis_inputs.system_loss_percent}.
        {monthlyConsumption !== null
          ? " Noktalı çizgi aylık tüketimdir; tüketimi aşan üretim şebekeye satılır."
          : ""}
      </figcaption>
    </figure>
  );
}

function PaybackFigures({ quote }: { quote: QuoteResponse }) {
  const { system_options: options } = quote;
  const lifetimeYears = quote.assumptions.financial.lifetime_years;
  const figureRange = options.length > 1 ? "Şekil 2–3" : "Şekil 2";
  return (
    <>
      <div className={styles.key}>
        <Key swatch={styles.kp}>Toplam fiyat (KDV dahil)</Key>
        <span>
          {options.length > 1
            ? "Daire (Seçenek 1) ve kare (Seçenek 2): geri ödeme noktası"
            : "Daire: geri ödeme noktası"}
        </span>
      </div>
      <div className={`${styles.multi} ${options.length === 1 ? styles.singleFigure : ""}`}>
        {options.map((option, index) => {
          const number = (index + 1) as 1 | 2;
          const chart = cumulativeSavingsChart(option);
          const headline = option.savings.payback_beyond_lifetime
            ? paybackText(option, lifetimeYears)
            : `${formatPaybackYears(option.savings.payback_period_years ?? 0)} içinde geri ödeme`;
          const last = chart.points.at(-1);
          const description = `Seçenek ${number}: toplam fiyat ${formatTry(chart.totalPriceTry)}, ${
            option.savings.payback_beyond_lifetime
              ? paybackText(option, lifetimeYears)
              : `geri ödeme ${formatPaybackYears(option.savings.payback_period_years ?? 0)}`
          }, ${chart.lastYear}. yılda birikimli net tasarruf ${formatTry(last?.cumulativeNetSavingsTry ?? 0)}.`;
          return (
            <figure key={index} className={styles.figure}>
              <p className={number === 1 ? styles.kickOne : styles.kickTwo}>Seçenek {number}</p>
              <p className={styles.figureTitle}>{headline}</p>
              <div role="img" aria-label={description}>
                <CumulativeSavingsChart option={option} number={number} />
              </div>
            </figure>
          );
        })}
      </div>
      <figure className={styles.figure}>
        <figcaption>
          <b>{figureRange}</b>
          Birikimli net tasarruf (TL), bugünün lirasıyla, {lifetimeYears} yıl.{" "}
          {options.length > 1 ? "Her seçenek kendi ölçeğinde çizilmiştir; " : ""}eğri kesikli çizgiyi
          (toplam fiyat) geçtiği yıl geri ödeme süresidir. Evirici{" "}
          {quote.assumptions.financial.inverter_replacement_year}. yılda değiştirilir ve maliyeti net
          tasarruftan düşülür.
        </figcaption>
      </figure>
    </>
  );
}

function Assumptions({ quote }: { quote: QuoteResponse }) {
  const groups = assumptionGroups(quote.assumptions);
  return (
    <details className={styles.app}>
      <summary>
        <span className={styles.summaryTitle}>
          <small>Ek A</small>
          <span>Varsayımlar</span>
        </span>
        <span className={styles.toggle}>
          {assumptionCount(groups)} kalem ·{" "}
          <span className={styles.whenClosed}>göster</span>
          <span className={styles.whenOpen}>gizle</span>
        </span>
      </summary>
      <p className={styles.footnote}>
        Bu teklifte kullanılan kur, tarife, oran ve birim fiyatlar aşağıdadır; aynı girdi ve aynı
        varsayımlarla aynı teklif yeniden üretilir. Katalog ve fiyatlar placeholder veridir.
      </p>
      <div className={styles.assumptions}>
        {groups.map((group) => (
          <div key={group.title}>
            <h3>{group.title}</h3>
            <dl>
              {group.items.map((item) => (
                <div key={`${item.label}:${item.value}`}>
                  <dt>{item.label}</dt>
                  <dd>{item.value}</dd>
                </div>
              ))}
            </dl>
            {group.note ? <p className={styles.footnote}>{group.note}</p> : null}
          </div>
        ))}
      </div>
    </details>
  );
}

function Failure({ reason, id }: { reason: "unavailable" | "error"; id: string }) {
  const unavailable = reason === "unavailable";
  return (
    <article className="sheet" aria-labelledby="failure-title">
      <header className="letter">
        <div>
          <p className="kick">Güneş enerjisi teklifi</p>
          <h1 id="failure-title">Teklif</h1>
        </div>
      </header>
      <section className={styles.failure} role="alert">
        <h2>{unavailable ? "Teklif servisine ulaşılamadı" : "Teklif yüklenemedi"}</h2>
        <p>
          {unavailable
            ? "Servis şu anda yanıt vermiyor. Birkaç saniye sonra yeniden deneyin."
            : "Servis bir hata döndürdü. Sayfayı yeniden deneyin; sorun sürerse biraz sonra tekrar bakın."}
        </p>
        <p>
          <Link className="btn ghost" href={`/quotes/${id}`}>
            Tekrar dene <span aria-hidden="true">→</span>
          </Link>
        </p>
      </section>
    </article>
  );
}
