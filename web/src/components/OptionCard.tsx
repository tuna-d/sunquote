import type { SystemOptionResponse } from "@/api/types";
import { formatTry } from "@/lib/format";
import { CARD_ROWS, type OptionContext, paybackText, rowLabel, STRATEGY_LABELS } from "@/lib/optionRows";

import styles from "./QuoteDetailView.module.css";

/** One System Option as a card: the Payback Period is the headline, the price comes second, the details under them. */
export function OptionCard({
  option,
  number,
  context,
}: {
  option: SystemOptionResponse;
  number: 1 | 2;
  context: OptionContext;
}) {
  const headingId = `option-${number}-title`;
  const recovered = !option.savings.payback_beyond_lifetime;
  const payback = paybackText(option, context.lifetimeYears);
  return (
    <article className={styles.card} aria-labelledby={headingId}>
      <h3 id={headingId} className={number === 1 ? styles.kickOne : styles.kickTwo}>
        Seçenek {number} · {STRATEGY_LABELS[option.strategy]}
      </h3>
      <p className={recovered ? styles.big : styles.bigWords} data-headline="payback">
        {recovered ? <b>{payback}</b> : payback}
      </p>
      <p className={styles.cardNote}>Geri ödeme süresi</p>
      <p className={styles.pay}>
        <span>KDV dahil toplam bedel</span> <b>{formatTry(option.price.total_try)}</b>
      </p>
      <dl className={styles.facts}>
        {CARD_ROWS.map((row) => (
          <div key={row.id}>
            <dt>{rowLabel(row, context)}</dt>
            <dd>{row.value(option, context)}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}
