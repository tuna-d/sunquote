import styles from "./demo-banner.module.css";

/**
 * The warning that the demo is public. The Quote form and the Assistant chat both show it, above
 * their fields: nobody should type a real person's data into a page everyone can read.
 */
export function DemoBanner() {
  return (
    <div className={styles.banner} role="note" aria-labelledby="demo-banner-label">
      <b className={styles.label} id="demo-banner-label">
        Herkese açık demo
      </b>
      <span>
        Bu bir herkese açık demodur. Gerçek kişisel veri (ad, adres, telefon, e-posta) girmeyin;
        girilen teklifler her gece silinir.
      </span>
    </div>
  );
}
