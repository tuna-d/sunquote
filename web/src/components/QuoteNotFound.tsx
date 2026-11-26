import Link from "next/link";

/** Shown for a Quote id the API does not know, in place of the detail page. */
export function QuoteNotFound() {
  return (
    <article className="sheet" aria-labelledby="not-found-title">
      <header className="letter">
        <div>
          <p className="kick">404</p>
          <h1 id="not-found-title">Teklif bulunamadı</h1>
          <p className="sub">
            Bu numaralı teklif yok ya da silinmiş olabilir. Demodaki örnek olmayan teklifler her gece
            silinir.
          </p>
        </div>
      </header>
      <p style={{ marginTop: 32 }}>
        <Link className="btn ghost" href="/quotes">
          Tekliflere dön <span aria-hidden="true">→</span>
        </Link>
      </p>
    </article>
  );
}
