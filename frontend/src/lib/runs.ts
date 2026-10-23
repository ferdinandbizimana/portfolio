import type { Dashboard } from "./dashboard";

export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface RunSummary {
  id: number;
  analysis_key: string;
  analysis_title: string;
  analysis_version: string;
  label: string;
  status: RunStatus;
  progress: number;
  message: string;
  checks_passed: number;
  checks_total: number;
  created_at: string;
  finished_at: string | null;
}

export interface Run extends RunSummary {
  parameters: Record<string, unknown>;
  inputs: Record<string, { data_file_id: number; sheet: string; filename: string; sha256: string }>;
  errors: string[];
  checks: Dashboard["checks"];
  metrics: Dashboard["kpis"];
  dashboard: Dashboard | null;
  reports: { key: string; title: string; kind: string; filename: string; size_bytes: number }[];
  result_hash: string;
}

export interface AnalysisInfo {
  key: string;
  title: string;
  version: string;
  description: string;
  demo: boolean;
  inputs: {
    key: string;
    label: string;
    dataset: string;
    dataset_title: string;
    required: boolean;
    /** The input takes every sheet of the file recognised as the dataset. */
    all_sheets: boolean;
  }[];
  parameters_schema: {
    properties?: Record<
      string,
      {
        title?: string;
        description?: string;
        type?: string;
        format?: string;
        enum?: string[];
        default?: unknown;
      }
    >;
    required?: string[];
  };
}

export const STATUS_LABEL: Record<RunStatus, string> = {
  queued: "Waiting",
  running: "Running",
  succeeded: "Finished",
  failed: "Failed",
  cancelled: "Cancelled",
};

export function isActive(status: RunStatus): boolean {
  return status === "queued" || status === "running";
}

export function statusClass(status: RunStatus): string {
  if (status === "succeeded") return "bg-success-soft text-success";
  if (status === "failed") return "bg-danger-soft text-danger";
  return "bg-panel text-muted";
}
