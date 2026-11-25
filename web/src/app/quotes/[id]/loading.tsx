export default function Loading() {
  return (
    <article className="sheet" aria-busy="true" aria-live="polite">
      <header className="letter">
        <div>
          <p className="kick">Güneş enerjisi teklifi</p>
          <h1>Teklif</h1>
          <p className="sub">Teklif yükleniyor…</p>
        </div>
      </header>
    </article>
  );
}
