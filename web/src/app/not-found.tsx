import Link from "next/link";

export default function NotFound() {
  return (
    <article className="sheet">
      <header className="letter">
        <div>
          <p className="kick">404</p>
          <h1>Sayfa bulunamadı</h1>
          <p className="sub">Aradığınız sayfa yok ya da taşınmış.</p>
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
