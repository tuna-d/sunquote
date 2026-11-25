import Link from "next/link";

import type { QuoteListResult } from "@/api/quotes";
import type { QuoteListItem } from "@/api/types";
import {
  formatCapacityKwp,
  formatCreatedAt,
  formatLocation,
  formatOptionCount,
  formatTry,
} from "@/lib/format";
import { isEnabled } from "@/lib/navigation";
import { pageCount } from "@/lib/pagination";

import styles from "./QuoteListView.module.css";

function pageHref(page: number): string {
  return page <= 1 ? "/quotes" : `/quotes?page=${page}`;
}

/** The Quote list page's content for whatever the API answered. Pure: no data fetching here. */
export function QuoteListView({ result, page }: { result: QuoteListResult; page: number }) {
  return (
    <article className="sheet" aria-labelledby="list-title">
      <header className="letter">
        <div>
          <p className="kick">Güneş enerjisi teklifleri</p>
          <h1 id="list-title">Teklifler</h1>
          <p className="sub">Kayıtlı teklifler, en yeniden en eskiye.</p>
        </div>
        {result.ok && result.list.total > 0 ? (
          <dl className="meta">
            <div>
              <dt>Kayıtlı teklif</dt>
              <dd>{result.list.total}</dd>
            </div>
          </dl>
        ) : null}
      </header>
      <Body result={result} page={page} />
    </article>
  );
}

function Body({ result, page }: { result: QuoteListResult; page: number }) {
  if (!result.ok) {
    return <Failure reason={result.reason} page={page} />;
  }
  const { items, total, page_size: pageSize } = result.list;
  if (total === 0) {
    return <Empty />;
  }
  if (items.length === 0) {
    return <PastTheEnd />;
  }
  return (
    <>
      <QuoteTable items={items} />
      <Pager page={page} pages={pageCount(total, pageSize)} total={total} />
    </>
  );
}

function QuoteTable({ items }: { items: QuoteListItem[] }) {
  return (
    <table className={`t ${styles.table}`}>
      <caption>
        Tablo 1. Kayıtlı teklifler. Güç ve toplam bedel ilk seçeneğe aittir; tutarlar KDV dahil, tam
        lira olarak gösterilir.
      </caption>
      <thead>
        <tr>
          <th scope="col">Müşteri</th>
          <th scope="col">Teklif no</th>
          <th scope="col">Oluşturulma</th>
          <th scope="col">Seçenek</th>
          <th scope="col">Güç</th>
          <th scope="col">Toplam</th>
        </tr>
      </thead>
      <tbody>
        {items.map((quote) => (
          <QuoteRow key={quote.id} quote={quote} />
        ))}
      </tbody>
    </table>
  );
}

function QuoteRow({ quote }: { quote: QuoteListItem }) {
  const location = formatLocation(quote.district, quote.province);
  return (
    <tr>
      <th scope="row" className={styles.customer}>
        <Link href={`/quotes/${quote.id}`}>{quote.customer_name}</Link>
        {quote.is_sample ? <span className={styles.badge}>Örnek</span> : null}
        <span className={location ? styles.place : `${styles.place} ${styles.unknown}`}>
          {location ?? "Konum belirtilmemiş"}
        </span>
      </th>
      <td data-label="Teklif no">{quote.quote_number}</td>
      <td data-label="Oluşturulma">{formatCreatedAt(quote.created_at)}</td>
      <td data-label="Seçenek">{formatOptionCount(quote.system_option_count)}</td>
      <td data-label="Güç">{formatCapacityKwp(quote.capacity_kwp)}</td>
      <td data-label="Toplam">{formatTry(quote.total_try)}</td>
    </tr>
  );
}

function Pager({ page, pages, total }: { page: number; pages: number; total: number }) {
  if (pages <= 1) {
    return null;
  }
  return (
    <nav aria-label="Sayfalar" className={styles.pager}>
      <span>
        {page > 1 ? (
          <Link href={pageHref(page - 1)} rel="prev">
            <span aria-hidden="true">← </span>Önceki
          </Link>
        ) : null}
      </span>
      <span className={styles.position}>
        Sayfa {page} / {pages}
        <span className="sr"> · {total} teklif</span>
      </span>
      <span className={styles.next}>
        {page < pages ? (
          <Link href={pageHref(page + 1)} rel="next">
            Sonraki<span aria-hidden="true"> →</span>
          </Link>
        ) : null}
      </span>
    </nav>
  );
}

function Empty() {
  return (
    <section className={styles.state}>
      <h2>Henüz teklif yok</h2>
      <p>Oluşturulan teklifler burada, en yenisi en üstte olacak şekilde listelenir.</p>
      {isEnabled("/quotes/new") ? (
        <p>
          <Link className="btn" href="/quotes/new">
            Yeni teklif oluştur <span aria-hidden="true">→</span>
          </Link>
        </p>
      ) : null}
    </section>
  );
}

function PastTheEnd() {
  return (
    <section className={styles.state}>
      <h2>Bu sayfada teklif yok</h2>
      <p>İstenen sayfa son sayfanın ötesinde.</p>
      <p>
        <Link className="btn ghost" href="/quotes">
          İlk sayfaya dön <span aria-hidden="true">→</span>
        </Link>
      </p>
    </section>
  );
}

function Failure({ reason, page }: { reason: "unavailable" | "error"; page: number }) {
  const unavailable = reason === "unavailable";
  return (
    <section className={`${styles.state} ${styles.failure}`} role="alert">
      <h2>{unavailable ? "Teklif servisine ulaşılamadı" : "Teklifler yüklenemedi"}</h2>
      <p>
        {unavailable
          ? "Servis şu anda yanıt vermiyor. Birkaç saniye sonra yeniden deneyin."
          : "Servis bir hata döndürdü. Sayfayı yeniden deneyin; sorun sürerse biraz sonra tekrar bakın."}
      </p>
      <p>
        <Link className="btn ghost" href={pageHref(page)}>
          Tekrar dene <span aria-hidden="true">→</span>
        </Link>
      </p>
    </section>
  );
}
