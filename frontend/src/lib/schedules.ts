export type DateRuleValue = { rule: string };
export type ParameterValue = string | number | DateRuleValue;

export interface Schedule {
  id: number;
  name: string;
  analysis: string;
  analysis_title: string;
  enabled: boolean;
  trigger: "daily" | "new_files";
  run_time: string;
  weekdays: number[];
  inputs: Record<string, { pattern: string; sheet: string }>;
  parameters: Record<string, ParameterValue>;
  only_when_changed: boolean;
  notify: boolean;
  last_fired_on: string | null;
  last_message: string;
  last_checked_at: string | null;
  last_run_id: number | null;
  last_run_status: string | null;
  run_count: number;
}

export interface ScheduleOptions {
  date_rules: Record<string, string>;
  timezone: string;
  folder_enabled: boolean;
}

export interface FolderStatus {
  enabled: boolean;
  settle_seconds: number;
  interval_seconds: number;
  timezone: string;
  last_check: string | null;
  files: {
    id: number;
    filename: string;
    source_path: string | null;
    status: string;
    message: string;
    created_at: string;
  }[];
}

/** Monday first, as Python's date.weekday() counts. */
export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function isDateRule(value: unknown): value is DateRuleValue {
  return typeof value === "object" && value !== null && "rule" in value;
}

/** "Every day at 06:00", "Mon–Fri at 06:30", "Mon, Thu at 07:00", "When new files arrive". */
export function describeWhen(
  schedule: Pick<Schedule, "trigger" | "run_time" | "weekdays">,
): string {
  if (schedule.trigger === "new_files") return "When new files arrive";
  const days = [...schedule.weekdays].sort((a, b) => a - b);
  let label: string;
  if (days.length === 7) label = "Every day";
  else if (days.join() === "0,1,2,3,4") label = "Mon–Fri";
  else label = days.map((d) => WEEKDAYS[d]).join(", ");
  return `${label} at ${schedule.run_time}`;
}

export function describeParameter(value: ParameterValue, rules: Record<string, string>): string {
  return isDateRule(value) ? (rules[value.rule] ?? value.rule) : String(value);
}
