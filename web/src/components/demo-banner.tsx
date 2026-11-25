import styles from "./demo-banner.module.css";

/** The public-demo notice shown above the form and the chat. Gold fill, ink text. */
export function DemoBanner() {
  return (
    <div className={styles.note} role="note">
      <b>Herkese açık demo</b>
      <span>
        Bu bir herkese açık demodur. Gerçek kişisel veri (ad, adres, telefon, e-posta) girmeyin;
        girilen teklifler her gece silinir.
      </span>
    </div>
  );
}
