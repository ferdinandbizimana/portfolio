export interface AuditEvent {
  id: number;
  occurred_at: string;
  action: string;
  ip_address: string | null;
  detail: Record<string, unknown>;
}

export interface AuditPage {
  total: number;
  items: AuditEvent[];
}

const LABELS: Record<string, string> = {
  "auth.login": "Signed in",
  "auth.login_failed": "Failed sign-in",
  "auth.login_rate_limited": "Sign-in blocked (too many failures)",
  "auth.logout": "Signed out",
  "auth.password_changed": "Password changed",
};

export function actionLabel(action: string): string {
  return LABELS[action] ?? action;
}

export function isWarning(action: string): boolean {
  return action === "auth.login_failed" || action === "auth.login_rate_limited";
}

/** Human summary of the detail object, e.g. "email: a@b.c". */
export function detailText(detail: Record<string, unknown>): string {
  return Object.entries(detail)
    .map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join(" · ");
}

export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Africa/Kigali",
  }).format(new Date(iso));
}
