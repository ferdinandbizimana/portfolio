"use client";

import { BarChart, LineChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { SVGRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

import { compactNumber, formatValue, type Chart, type Row } from "@/lib/dashboard";

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  SVGRenderer,
]);

// Colour-blind-safe categorical palette that works on light and dark backgrounds.
const PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#8f63d6", "#e87ba4", "#0e9aa7"];

function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export function buildOption(chart: Chart, rows: Row[]): echarts.EChartsCoreOption {
  const shown = chart.limit ? rows.slice(0, chart.limit) : rows;
  const categories = shown.map((r) => String(r[chart.category] ?? ""));
  const ink = cssVar("--color-ink", "#0f1a1f");
  const muted = cssVar("--color-muted", "#4a5a62");
  const line = cssVar("--color-line", "#d5dfe2");
  const tooltip = {
    trigger: chart.type === "pie" ? "item" : "axis",
    valueFormatter: (v: unknown) => formatValue(typeof v === "number" ? v : null, chart.format),
  };
  if (chart.type === "pie") {
    const series = chart.series[0];
    return {
      color: PALETTE,
      tooltip,
      legend: { bottom: 0, textStyle: { color: muted } },
      series: [
        {
          type: "pie",
          radius: ["40%", "70%"],
          data: shown.map((r) => ({
            name: String(r[chart.category] ?? ""),
            value: Number(series ? r[series.field] : 0) || 0,
          })),
          label: { color: ink },
        },
      ],
    };
  }
  const horizontal = chart.type === "bar" || chart.type === "stacked-bar";
  const valueAxis = {
    type: "value",
    splitNumber: horizontal ? 4 : 5,
    axisLabel: { color: muted, hideOverlap: true, formatter: (v: number) => compactNumber(v) },
    splitLine: { lineStyle: { color: line } },
  };
  const categoryAxis = {
    type: "category",
    data: categories,
    inverse: horizontal, // largest first, read top to bottom
    // Columns: name every category (a few, wrapped under their column); bars: names beside them.
    axisLabel: horizontal
      ? { color: ink, width: 140, overflow: "truncate" }
      : {
          color: ink,
          width: 96,
          overflow: "break",
          interval: categories.length <= 12 ? 0 : "auto",
        },
    axisLine: { lineStyle: { color: line } },
  };
  return {
    color: PALETTE,
    tooltip,
    legend: chart.series.length > 1 ? { bottom: 0, textStyle: { color: muted } } : undefined,
    grid: {
      left: 8,
      right: 16,
      top: 8,
      bottom: chart.series.length > 1 ? 32 : 8,
      containLabel: true,
    },
    xAxis: horizontal ? valueAxis : categoryAxis,
    yAxis: horizontal ? categoryAxis : valueAxis,
    series: chart.series.map((s) => ({
      name: s.name,
      type: chart.type === "line" ? "line" : "bar",
      stack: chart.type === "stacked-bar" ? "total" : undefined,
      data: shown.map((r) => Number(r[s.field]) || 0),
      barMaxWidth: 28,
    })),
  };
}

export function EChart({ chart, rows }: { chart: Chart; rows: Row[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const instance = echarts.init(ref.current, undefined, { renderer: "svg" });
    instance.setOption(buildOption(chart, rows));
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      instance.dispose();
    };
  }, [chart, rows]);

  const count = chart.limit ? Math.min(rows.length, chart.limit) : rows.length;
  const height =
    chart.type === "bar" || chart.type === "stacked-bar" ? Math.max(200, count * 28 + 40) : 320;
  return (
    <figure className="rounded-lg border border-line p-4">
      <figcaption className="mb-2 text-sm font-semibold">{chart.title}</figcaption>
      <div ref={ref} style={{ height }} role="img" aria-label={chart.title} />
    </figure>
  );
}
