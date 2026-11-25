import { parseDecimal } from "@/lib/quote-form";

import styles from "./QuoteForm.module.css";

/** The eight compass points, azimuth in degrees (0 = north, 180 = south). */
const POINTS = [
  { short: "K", name: "Kuzey", deg: 0 },
  { short: "KD", name: "Kuzeydoğu", deg: 45 },
  { short: "D", name: "Doğu", deg: 90 },
  { short: "GD", name: "Güneydoğu", deg: 135 },
  { short: "G", name: "Güney", deg: 180 },
  { short: "GB", name: "Güneybatı", deg: 225 },
  { short: "B", name: "Batı", deg: 270 },
  { short: "KB", name: "Kuzeybatı", deg: 315 },
] as const;

/** The compass point closest to a bearing, and how far off it is (degrees, 0 to 180). */
function nearestPoint(degrees: number) {
  const offBy = (deg: number) => Math.abs((((degrees - deg + 540) % 360) + 360) % 360 - 180);
  const point = POINTS.reduce((best, next) => (offBy(next.deg) < offBy(best.deg) ? next : best));
  return { point, distance: offBy(point.deg) };
}

const decimalComma = (value: number) => String(value).replace(".", ",");

const TICKS = Array.from({ length: 24 }, (_, index) => {
  const angle = (index * 15 * Math.PI) / 180;
  const major = index % 6 === 0;
  const inner = major ? 50 : 52;
  const outer = major ? 58 : 56;
  return {
    key: index,
    major,
    x1: (Math.sin(angle) * inner).toFixed(1),
    y1: (-Math.cos(angle) * inner).toFixed(1),
    x2: (Math.sin(angle) * outer).toFixed(1),
    y2: (-Math.cos(angle) * outer).toFixed(1),
  };
});

interface CompassPickerProps {
  id: string;
  /** The degrees as typed. */
  value: string;
  onChange: (value: string) => void;
  error: string | undefined;
}

/**
 * The Roof's azimuth: a dial and eight compass points that fill in the degrees, and the degrees
 * themselves for any bearing in between. The text field is the value; the rest is a shortcut.
 */
export function CompassPicker({ id, value, onChange, error }: CompassPickerProps) {
  const decimal = parseDecimal(value);
  const degrees = decimal === null ? null : Number(decimal);
  const nearest = degrees === null ? null : nearestPoint(degrees);
  const errorId = `e-${id}`;
  const readoutId = `r-${id}`;

  return (
    <div>
      <label className={styles.fl} htmlFor={id}>
        Yön (azimut) <span className={styles.req} aria-hidden="true">*</span>
        <small>180° güney</small>
      </label>
      <div className={styles.compass}>
        <svg className={styles.dial} viewBox="-64 -64 128 128" width="124" height="124" aria-hidden="true">
          <circle r="60" fill="none" stroke="var(--ink)" strokeWidth="1" />
          {TICKS.map((tick) => (
            <line
              key={tick.key}
              x1={tick.x1}
              y1={tick.y1}
              x2={tick.x2}
              y2={tick.y2}
              stroke="var(--ink)"
              strokeWidth={tick.major ? 1.6 : 0.8}
            />
          ))}
          {[
            { label: "K", x: 0, y: -33 },
            { label: "D", x: 38, y: 5 },
            { label: "G", x: 0, y: 43 },
            { label: "B", x: -38, y: 5 },
          ].map((letter) => (
            <text
              key={letter.label}
              x={letter.x}
              y={letter.y}
              textAnchor="middle"
              fontFamily="var(--serif)"
              fontStyle="italic"
              fontSize="15"
              fill="var(--ink)"
            >
              {letter.label}
            </text>
          ))}
          {degrees !== null ? (
            <g transform={`rotate(${degrees} 0 0)`}>
              <path d="M0,-26 L3.5,0 L0,-4 L-3.5,0Z" fill="var(--accent)" />
              <path d="M0,26 L3.5,0 L0,4 L-3.5,0Z" fill="var(--rule-strong)" />
            </g>
          ) : null}
          <circle r="2" fill="var(--ink)" />
        </svg>
        <div>
          <div className={styles.points} role="radiogroup" aria-label="Pusula yönü">
            {POINTS.map((point) => (
              <label key={point.deg} className={styles.point}>
                <input
                  type="radio"
                  name={`${id}-point`}
                  checked={nearest !== null && nearest.distance === 0 && nearest.point === point}
                  onChange={() => onChange(String(point.deg))}
                />
                <span aria-hidden="true">{point.short}</span>
                <span className="sr">{point.name}</span>
              </label>
            ))}
          </div>
          <div className={styles.unit} style={{ marginTop: 14 }}>
            <input
              id={id}
              className={`${styles.input} ${styles.short}`}
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={value}
              onChange={(event) => onChange(event.target.value)}
              aria-invalid={error ? true : undefined}
              aria-describedby={[readoutId, error ? errorId : null].filter(Boolean).join(" ")}
            />
            <span>derece</span>
          </div>
          <p className={styles.readout} id={readoutId} role="status">
            {degrees === null || nearest === null
              ? "—"
              : `${decimalComma(degrees)}° · ${nearest.distance === 0 ? "" : "en yakın yön: "}${nearest.point.name}`}
          </p>
        </div>
      </div>
      {error ? (
        <p className={styles.err} id={errorId}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
