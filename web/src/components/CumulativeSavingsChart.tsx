"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { cumulativeSavingsChart, formatAxisTry } from "@/lib/charts";
import type { SystemOptionResponse } from "@/api/types";
import { formatPaybackYears, formatTry } from "@/lib/format";

import { AXIS_LINE, AXIS_TICK, GRID, SERIES, TOOLTIP_STYLE } from "./chartStyle";
import styles from "./QuoteDetailView.module.css";

const LABEL_HALO = {
  fill: "var(--ink)",
  fontFamily: "var(--sans)",
  fontSize: 12,
  fontWeight: 700,
  paintOrder: "stroke",
  stroke: "var(--paper)",
  strokeWidth: 4,
  strokeLinejoin: "round",
} as const;

/** The payback marker: a circle for option 1, a square for option 2. */
function PaybackMarker({
  cx,
  cy,
  number,
}: {
  cx?: number;
  cy?: number;
  number: 1 | 2;
}) {
  if (cx === undefined || cy === undefined) {
    return null;
  }
  const color = SERIES[number - 1];
  return number === 1 ? (
    <circle cx={cx} cy={cy} r={5} fill="var(--paper)" stroke={color} strokeWidth={2.5} />
  ) : (
    <rect x={cx - 5} y={cy - 5} width={10} height={10} fill="var(--paper)" stroke={color} strokeWidth={2.5} />
  );
}

/**
 * One option's cumulative net savings over the lifetime against the total price. Option 1 is a
 * solid line with a circle marker, option 2 a dashed line with a square one; the price is the
 * thin dashed ink line, labelled directly. The two cross at the payback.
 */
export function CumulativeSavingsChart({
  option,
  number,
}: {
  option: SystemOptionResponse;
  number: 1 | 2;
}) {
  const chart = cumulativeSavingsChart(option);
  const years = Array.from({ length: Math.floor(chart.lastYear / 5) + 1 }, (_, index) => index * 5);
  const last = chart.points.at(-1);
  const color = SERIES[number - 1];
  return (
    <div className={styles.chart}>
      <ResponsiveContainer width="100%" height={300} initialDimension={{ width: 380, height: 300 }}>
        <LineChart data={chart.points} margin={{ top: 28, right: 24, bottom: 20, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis
            type="number"
            dataKey="year"
            domain={[0, chart.lastYear]}
            ticks={years}
            tick={AXIS_TICK}
            axisLine={AXIS_LINE}
            tickLine={AXIS_LINE}
            label={{ value: "yıl", position: "insideBottomRight", offset: -2, style: AXIS_TICK.style }}
          />
          <YAxis
            type="number"
            domain={[0, "auto"]}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
            width={60}
            tickFormatter={formatAxisTry}
          />
          <Tooltip
            cursor={{ stroke: "var(--rule-strong)" }}
            contentStyle={TOOLTIP_STYLE}
            labelFormatter={(year) => `${year}. yıl`}
            formatter={(value) => [formatTry(Number(value)), "Birikimli net tasarruf"]}
          />
          <ReferenceLine
            y={chart.totalPriceTry}
            ifOverflow="extendDomain"
            stroke="var(--ink)"
            strokeWidth={1.3}
            strokeDasharray="5 4"
            label={{
              value: `toplam fiyat ${formatTry(chart.totalPriceTry)}`,
              position: "insideBottomRight",
              offset: 8,
              style: LABEL_HALO,
            }}
          />
          <Line
            type="linear"
            dataKey="cumulativeNetSavingsTry"
            stroke={color}
            strokeWidth={2.5}
            strokeDasharray={number === 2 ? "10 4" : undefined}
            dot={false}
            activeDot={{ r: 4, fill: color }}
            isAnimationActive={false}
          />
          {last ? (
            <ReferenceDot
              x={last.year}
              y={last.cumulativeNetSavingsTry}
              r={0}
              label={{
                value: formatTry(last.cumulativeNetSavingsTry),
                position: "left",
                offset: 8,
                style: LABEL_HALO,
              }}
            />
          ) : null}
          {chart.payback ? (
            <>
              <ReferenceLine
                segment={[
                  { x: chart.payback.year, y: 0 },
                  { x: chart.payback.year, y: chart.payback.valueTry },
                ]}
                stroke={color}
                strokeWidth={1.5}
                strokeDasharray="2 3"
              />
              <ReferenceDot
                x={chart.payback.year}
                y={chart.payback.valueTry}
                shape={(props: { cx?: number; cy?: number }) => (
                  <PaybackMarker cx={props.cx} cy={props.cy} number={number} />
                )}
                label={{
                  value: formatPaybackYears(chart.payback.year),
                  position: "right",
                  offset: 12,
                  style: LABEL_HALO,
                }}
              />
            </>
          ) : null}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
