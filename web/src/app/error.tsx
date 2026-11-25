"use client";

// The last resort for an error no page handled itself. Pages that fetch data (the Quote list)
// render their own failure states, with a message that names the cause.
export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <article className="sheet" role="alert">
      <header className="letter">
        <div>
          <p className="kick">Hata</p>
          <h1>Bir şeyler ters gitti</h1>
          <p className="sub">Sayfa gösterilemedi. Yeniden deneyin.</p>
        </div>
      </header>
      <p style={{ marginTop: 32 }}>
        <button type="button" className="btn ghost" onClick={reset}>
          Tekrar dene
        </button>
      </p>
    </article>
  );
}
