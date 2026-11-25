"use client";

import Link from "next/link";
import { type FormEvent, useRef, useState } from "react";

import {
  type AssistantFailure,
  type AssistantResult,
  type ChatMessage,
  MAX_MESSAGE_CHARACTERS,
  MAX_MESSAGES,
  sendAssistantMessages,
} from "@/api/assistant";
import type { MissingField, QuoteReference } from "@/api/types";

import styles from "./AssistantChat.module.css";
import { DemoBanner } from "./demo-banner";

/** The chat's send function; tests pass a fake. */
export type SendMessages = (messages: ChatMessage[]) => Promise<AssistantResult>;

/** A message as the chat shows it: the API's fields travel with the Assistant's turn. */
interface Turn extends ChatMessage {
  quote?: QuoteReference;
  missingFields?: MissingField[];
}

const FIELD_LABELS: Record<MissingField, string> = {
  "customer.name": "Müşteri adı",
  "site.address": "Adres",
  "roof.roof_type": "Çatı tipi",
  "roof.tilt_deg": "Çatı eğimi",
  "roof.azimuth_deg": "Çatı yönü",
  "roof.usable_area_m2": "Kullanılabilir alan",
  consumption: "Elektrik tüketimi",
  subscriber_group: "Abone grubu",
};

function waitText(seconds: number | undefined): string {
  if (seconds === undefined) {
    return "Biraz sonra yeniden deneyin.";
  }
  const minutes = Math.ceil(seconds / 60);
  return minutes <= 1
    ? "Yaklaşık 1 dakika sonra yeniden deneyin."
    : `Yaklaşık ${minutes} dakika sonra yeniden deneyin.`;
}

function failureText(
  kind: AssistantFailure,
  retryAfterSeconds?: number,
): { title: string; body: string } {
  switch (kind) {
    case "not-configured":
      return {
        title: "Asistan yapılandırılmamış",
        body: "Bu ortamda Asistan’ın yapay zekâ anahtarı tanımlı değil. Teklifi “Yeni teklif” formundan oluşturabilirsiniz.",
      };
    case "unavailable":
      return {
        title: "Asistan şu anda yanıt veremiyor",
        body: "Yapay zekâ servisi geçici olarak kullanılamıyor. Mesajınız korundu; birazdan yeniden gönderin ya da formu kullanın.",
      };
    case "budget-exhausted":
      return {
        title: "Günlük kullanım sınırı doldu",
        body: "Demonun günlük Asistan sınırı bitti; sınır her gece 00:00’da (İstanbul saati) yenilenir. Bu arada “Yeni teklif” formunu kullanabilirsiniz.",
      };
    case "rate-limited":
      return {
        title: "Çok fazla mesaj gönderildi",
        body: `Saatlik mesaj sınırına ulaştınız. ${waitText(retryAfterSeconds)}`,
      };
    case "invalid":
      return {
        title: "Mesaj kabul edilmedi",
        body: "Konuşma geçersiz görünüyor. Yeni bir konuşma başlatıp tekrar deneyin.",
      };
    case "network":
      return {
        title: "Servise ulaşılamadı",
        body: "Teklif servisine ulaşılamadı. Bağlantınızı kontrol edip mesajınızı yeniden gönderin.",
      };
    case "error":
      return {
        title: "Bir sorun oluştu",
        body: "Servis beklenmeyen bir hata döndürdü. Mesajınız korundu; yeniden göndermeyi deneyin.",
      };
  }
}

export function AssistantChat({ send = sendAssistantMessages }: { send?: SendMessages }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<{
    kind: AssistantFailure;
    retryAfterSeconds?: number;
  } | null>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);

  const full = turns.length >= MAX_MESSAGES;
  const canSend = !pending && !full && draft.trim().length > 0;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSend) {
      return;
    }
    const content = draft.trim();
    const history = turns.map(({ role, content: text }) => ({ role, content: text }));
    setTurns([...turns, { role: "user", content }]);
    setDraft("");
    setFailure(null);
    setPending(true);
    const result = await send([...history, { role: "user", content }]);
    setPending(false);
    if (result.ok) {
      const { reply, quote, missing_fields: missing } = result.response;
      setTurns((current) => [
        ...current,
        {
          role: "assistant",
          content: reply,
          ...(quote ? { quote } : {}),
          ...(missing.length > 0 ? { missingFields: missing } : {}),
        },
      ]);
    } else {
      // Take the message back out of the history so a retry sends a valid conversation.
      setTurns(turns);
      setDraft(content);
      setFailure({
        kind: result.kind,
        ...(result.retryAfterSeconds === undefined
          ? {}
          : { retryAfterSeconds: result.retryAfterSeconds }),
      });
    }
  }

  function restart() {
    setTurns([]);
    setDraft("");
    setFailure(null);
    draftRef.current?.focus();
  }

  const failureCopy = failure ? failureText(failure.kind, failure.retryAfterSeconds) : null;

  return (
    <article className="sheet" aria-labelledby="assistant-title">
      <header className="letter">
        <div>
          <p className="kick">Türkçe sohbet</p>
          <h1 id="assistant-title">Asistan</h1>
          <p className="sub">
            Müşteriyi ve çatıyı kendi cümlelerinizle anlatın; eksikleri sorayım.
          </p>
        </div>
        <dl className="meta">
          <div>
            <dt>Mesaj</dt>
            <dd>
              {turns.length} / {MAX_MESSAGES}
            </dd>
          </div>
        </dl>
      </header>

      <DemoBanner />

      <ol className={styles.log} aria-label="Konuşma">
        {turns.length === 0 ? (
          <li className={styles.hint}>
            Örnek: “Ankara Çankaya’da Elif Yıldırım için, 80 m² düz çatı, aylık yaklaşık 450 kWh
            tüketim, mesken aboneliği.”
          </li>
        ) : null}
        {turns.map((turn, index) => (
          <li key={index} className={turn.role === "user" ? styles.user : styles.assistant}>
            <p className={styles.speaker}>{turn.role === "user" ? "Siz" : "Asistan"}</p>
            <p className={styles.text}>{turn.content}</p>
            {turn.missingFields ? (
              <ul className={styles.chips} aria-label="Eksik bilgiler">
                {turn.missingFields.map((field) => (
                  <li key={field}>{FIELD_LABELS[field]}</li>
                ))}
              </ul>
            ) : null}
            {turn.quote ? <QuoteCard quote={turn.quote} /> : null}
          </li>
        ))}
      </ol>

      {pending ? (
        <p role="status" className={styles.pending}>
          Yanıt hazırlanıyor… Teklif hesaplanırken bu yarım dakikayı bulabilir.
        </p>
      ) : null}

      {failureCopy ? (
        <section className={styles.failure} role="alert">
          <h2>{failureCopy.title}</h2>
          <p>{failureCopy.body}</p>
        </section>
      ) : null}

      <form className={styles.composer} onSubmit={submit}>
        <label className={styles.label} htmlFor="chat-message">
          Mesajınız
        </label>
        <textarea
          id="chat-message"
          ref={draftRef}
          className={styles.input}
          rows={3}
          maxLength={MAX_MESSAGE_CHARACTERS}
          value={draft}
          disabled={full}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
              event.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <div className={styles.actions}>
          <span className={styles.count}>
            {draft.length} / {MAX_MESSAGE_CHARACTERS}
          </span>
          {turns.length > 0 ? (
            <button type="button" className="btn ghost" onClick={restart}>
              Yeni konuşma
            </button>
          ) : null}
          <button type="submit" className="btn" disabled={!canSend}>
            Gönder <span aria-hidden="true">→</span>
          </button>
        </div>
        {full ? (
          <p className={styles.limit}>
            Konuşma {MAX_MESSAGES} mesaj sınırına ulaştı. Devam etmek için yeni bir konuşma
            başlatın.
          </p>
        ) : null}
      </form>
    </article>
  );
}

function QuoteCard({ quote }: { quote: QuoteReference }) {
  return (
    <div className={styles.card} role="group" aria-label={`Teklif ${quote.quote_number}`}>
      <p className="kick accent">Teklif oluşturuldu</p>
      <p className={styles.number}>{quote.quote_number}</p>
      <p className={styles.links}>
        <Link className="btn" href={`/quotes/${quote.id}`}>
          Teklifi aç <span aria-hidden="true">→</span>
        </Link>
        <a className="btn ghost" href={quote.document_url} target="_blank" rel="noreferrer">
          Teklif belgesi <span aria-hidden="true">↗</span>
        </a>
      </p>
    </div>
  );
}
