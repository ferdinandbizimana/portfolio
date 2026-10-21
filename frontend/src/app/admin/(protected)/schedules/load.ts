import "server-only";

import type { AnalysisInfo } from "@/lib/runs";
import type { ScheduleOptions } from "@/lib/schedules";
import { apiGet } from "@/lib/server-api";

/** What the schedule form needs: the analyses and the date rules. */
export async function loadFormData(): Promise<{
  analyses: AnalysisInfo[];
  options: ScheduleOptions;
} | null> {
  const [analyses, options] = await Promise.all([
    apiGet("/api/admin/analyses"),
    apiGet("/api/admin/schedules/options"),
  ]);
  if (!analyses.ok || !options.ok) return null;
  return {
    analyses: (await analyses.json()) as AnalysisInfo[],
    options: (await options.json()) as ScheduleOptions,
  };
}
