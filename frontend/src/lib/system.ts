export type SystemState = "ok" | "warning" | "error" | "off";

export interface SystemStatus {
  version: string;
  items: { name: string; state: SystemState; detail: string }[];
}

export const STATE_LABEL: Record<SystemState, string> = {
  ok: "OK",
  warning: "Check",
  error: "Problem",
  off: "Not set up",
};

export const STATE_CLASS: Record<SystemState, string> = {
  ok: "bg-success-soft text-success",
  warning: "bg-panel text-ink border border-line",
  error: "bg-danger-soft text-danger",
  off: "bg-panel text-muted border border-line",
};
