"use client";

import { useId } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MonthlyRow } from "@/lib/charts";
import { formatKwh } from "@/lib/format";

import { AXIS_LINE, AXIS_TICK, GRID, SERIES, TOOLTIP_STYLE } from "./chartStyle";
import styles from "./QuoteDetailView.module.css";

/**
 * Figure 1: monthly production, one bar per System Option. Option 1 is a solid bar, option 2 is
 * hatched, so the two read apart without colour. The dotted line is the Customer's monthly
 * consumption when the Quote has one.
 */
export function ProductionChart({
  rows,
  monthlyConsumptionKwh,
}: {
  rows: MonthlyRow[];
  monthlyConsumptionKwh: number | null;
}) {
  const patternId = `hatch-${useId().replace(/:/g, "")}`;
  const optionCount = rows[0]?.values.length ?? 0;
  const data = rows.map((row) => ({
    month: row.month,
    fullMonth: row.fullMonth,
    option1: row.values[0] ?? 0,
    option2: row.values[1] ?? 0,
  }));
  return (
    <div className={styles.chart} data-testid="production-chart">
      <ResponsiveContainer width="100%" height={300} initialDimension={{ width: 760, height: 300 }}>
        <BarChart data={data} margin={{ top: 24, right: 8, bottom: 4, left: 0 }} barGap={2}>
          <defs>
            <pattern
              id={patternId}
              width="5"
              height="5"
              patternUnits="userSpaceOnUse"
              patternTransform="rotate(45)"
            >
              <rect width="5" height="5" fill={SERIES[1]} />
              <rect width="2" height="5" fill="var(--paper)" />
            </pattern>
          </defs>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis
            dataKey="month"
            interval={0}
            tick={AXIS_TICK}
            axisLine={AXIS_LINE}
            tickLine={false}
          />
          <YAxis
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
            width={56}
            tickFormatter={(value: number) => new Intl.NumberFormat("tr-TR").format(value)}
          />
          <Tooltip
            cursor={{ fill: "var(--wash)" }}
            contentStyle={TOOLTIP_STYLE}
            labelFormatter={(_, payload) => payload[0]?.payload.fullMonth ?? ""}
            formatter={(value, name) => [formatKwh(Number(value)), name]}
          />
          <Bar
            dataKey="option1"
            name="Seçenek 1"
            fill={SERIES[0]}
            isAnimationActive={false}
            maxBarSize={22}
          />
          {optionCount > 1 ? (
            <Bar
              dataKey="option2"
              name="Seçenek 2"
              fill={`url(#${patternId})`}
              stroke={SERIES[1]}
              strokeWidth={1}
              isAnimationActive={false}
              maxBarSize={22}
            />
          ) : null}
          {monthlyConsumptionKwh !== null ? (
            <ReferenceLine
              y={monthlyConsumptionKwh}
              ifOverflow="extendDomain"
              stroke="var(--ink-2)"
              strokeWidth={1.8}
              strokeDasharray="2 4"
            />
          ) : null}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
