/** Types and helpers for dashboards returned by analyses (see backend app/analyses/dashboard.py). */

export type ValueFormat = "number" | "integer" | "money" | "percent" | "text" | "date";
export type CellValue = string | number | boolean | null;
export type Row = Record<string, CellValue>;

export interface Kpi {
  label: string;
  value: CellValue;
  format: ValueFormat;
  unit: string;
  note: string;
}

export interface Column {
  key: string;
  label: string;
  format: ValueFormat;
}

export interface Table {
  id: string;
  title: string;
  columns: Column[];
  rows: Row[];
  level: "summary" | "detail";
  filters: string[];
  searchable: string[];
  note: string;
}

export interface Chart {
  id: string;
  title: string;
  type: "bar" | "column" | "line" | "pie" | "stacked-bar";
  table: string;
  category: string;
  series: { name: string; field: string }[];
  format: ValueFormat;
  limit: number | null;
}

export interface Check {
  key: string;
  label: string;
  expected: number;
  actual: number;
  tolerance: number;
  passed: boolean;
  description: string;
}

export interface Dashboard {
  title: string;
  subtitle: string;
  kpis: Kpi[];
  charts: Chart[];
  tables: Table[];
  checks: Check[];
  notes: string[];
}

const NUMBER = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });
const WHOLE = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });

/** A value as shown in dashboards: negatives in brackets for amounts, like the reports. */
export function formatValue(value: CellValue | undefined, format: ValueFormat): string {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "number") {
    switch (format) {
      case "money":
        return value < 0 ? `(${WHOLE.format(-value)})` : WHOLE.format(value);
      case "number":
        return value < 0 ? `(${NUMBER.format(-value)})` : NUMBER.format(value);
      case "integer":
        return WHOLE.format(value);
      case "percent":
        return `${(value * 100).toFixed(1)}%`;
      default:
        return String(value);
    }
  }
  if (format === "date" && typeof value === "string" && /^\d{4}-\d{2}-\d{2}/.test(value)) {
    const [y, m, d] = value.slice(0, 10).split("-");
    return `${d}.${m}.${y}`;
  }
  return String(value);
}

/** Short form for chart axes: 1.2M, 350K. */
export function compactNumber(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(1)}bn`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(0)}K`;
  return `${sign}${abs.toFixed(abs % 1 ? 1 : 0)}`;
}

/** Rows that pass the chosen filter values and the search text. */
export function filterRows(table: Table, filters: Record<string, string>, search: string): Row[] {
  const needle = search.trim().toLowerCase();
  return table.rows.filter((row) => {
    for (const [key, wanted] of Object.entries(filters)) {
      if (wanted && table.columns.some((c) => c.key === key) && String(row[key] ?? "") !== wanted)
        return false;
    }
    if (!needle) return true;
    const keys = table.searchable.length ? table.searchable : table.columns.map((c) => c.key);
    return keys.some((key) =>
      String(row[key] ?? "")
        .toLowerCase()
        .includes(needle),
    );
  });
}

/** Distinct values of a column, sorted, for a filter drop-down. */
export function distinctValues(rows: Row[], key: string): string[] {
  const values = new Set<string>();
  for (const row of rows) {
    const value = row[key];
    if (value !== null && value !== undefined && value !== "") values.add(String(value));
  }
  return [...values].sort((a, b) => a.localeCompare(b, "en", { numeric: true }));
}
