/**
 * Chart styling from the design tokens (docs/design/tokens-2c.md). Recharts writes these onto
 * SVG elements as styles, so the colours stay `var(--token)` and follow `globals.css`.
 * Gold is never a series or a line.
 */

export const SERIES = ["var(--series-1)", "var(--series-2)"] as const;

export const GRID = "var(--grid)";

export const AXIS_LINE = { stroke: "var(--ink)", strokeWidth: 1 } as const;

export const AXIS_TICK = {
  style: { fill: "var(--ink-2)", fontFamily: "var(--sans)", fontSize: 12 },
} as const;

export const TOOLTIP_STYLE = {
  borderRadius: 0,
  border: "1px solid var(--ink)",
  background: "var(--paper)",
  color: "var(--ink)",
  fontFamily: "var(--sans)",
  fontSize: 13,
  boxShadow: "none",
} as const;
