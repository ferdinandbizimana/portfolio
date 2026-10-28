// Spot-check variance follow-up: shapes returned by /api/admin/variances and
// /api/public/variances, and how a case is shown.

export type Colour = "green" | "amber" | "red";

export interface VarianceCase {
  id: number;
  source: string;
  source_title: string;
  reference: string;
  storage_bin: string;
  product: string;
  description: string;
  batch: string;
  system_qty: number | null;
  counted_qty: number | null;
  difference_qty: number;
  found_on: string | null;
  reported_by: string;
  staff_id: number | null;
  staff_name: string;
  status: "open" | "corrected";
  colour: Colour;
  days_open: number;
  reason: string;
  root_cause: string;
  corrected_qty: number | null;
  responsible_unit: string;
  action_taken: string;
  corrected_by: string;
  corrected_at: string | null;
  created_at: string;
  notified_at: string | null;
}

export interface VarianceStaff {
  id: number;
  name: string;
  email: string;
  active: boolean;
  bins: number;
}

export interface PersonSummary {
  staff_id: number | null;
  name: string;
  open: number;
  overdue: number;
  corrected: number;
}

export interface VarianceOverview {
  summary: PersonSummary[];
  staff: VarianceStaff[];
  cases: VarianceCase[];
  total: number;
  units: string[];
  root_causes: string[];
  sources: Record<string, string>;
  overdue_days: number;
  bins: number;
  /** New variances waiting for the day-close e-mail. */
  pending: number;
  day_close_time: string;
  progress: AccuracyProgress[];
}

/** Accuracy of one imported file, before and after the corrections recorded. */
export interface AccuracyProgress {
  file: string;
  source: string;
  imported_at: string;
  lines: number;
  variances: number;
  corrected: number;
  open: number;
  line_accuracy_before: number | null;
  line_accuracy_now: number | null;
  quantity_accuracy_before: number | null;
  quantity_accuracy_now: number | null;
}

/** "98.5%", or "—" when there was nothing to measure. */
export function formatPercent(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

export interface PublicVariance {
  storage_bin: string;
  product: string;
  description: string;
  batch: string;
  source_title: string;
  system_qty: number | null;
  counted_qty: number | null;
  difference_qty: number;
  found_on: string | null;
  responsible: string;
  status: "open" | "corrected";
  colour: Colour;
  days_open: number;
  overdue_days: number;
  reason: string;
  root_cause: string;
  corrected_qty: number | null;
  responsible_unit: string;
  action_taken: string;
  corrected_by: string;
  corrected_at: string | null;
  units: string[];
  root_causes: string[];
}

export const COLOUR_LABEL: Record<Colour, string> = {
  green: "Corrected",
  amber: "Open",
  red: "Overdue",
};

export const COLOUR_CLASS: Record<Colour, string> = {
  green: "bg-success-soft text-success",
  amber: "bg-warning-soft text-warning",
  red: "bg-danger-soft text-danger",
};

/** "-2" / "+5": the sign shows missing or extra stock. */
export function formatDifference(value: number): string {
  const text = Number.isInteger(value) ? String(Math.abs(value)) : Math.abs(value).toFixed(2);
  return value > 0 ? `+${text}` : value < 0 ? `-${text}` : "0";
}

/** The status line shown for a case, e.g. "Open for 3 days (overdue after 2)". */
export function statusLine(c: { colour: Colour; days_open: number }, overdueDays: number): string {
  if (c.colour === "green") return "Corrected";
  const days = `${c.days_open} day${c.days_open === 1 ? "" : "s"}`;
  return c.colour === "red"
    ? `Overdue: open for ${days} (more than ${overdueDays})`
    : `Open for ${days} (overdue after ${overdueDays})`;
}

/** The problem returned by an import (a message and the rows that are wrong). */
export function importProblem(body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const { message, errors } = detail as { message: string; errors?: string[] };
    return [message, ...(errors ?? []).slice(0, 5)].join(" ");
  }
  return "The file could not be imported.";
}
