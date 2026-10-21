export type CheckState = "ok" | "error";

export interface Health {
  status: "ok" | "degraded" | "unreachable";
  checks: Record<string, CheckState>;
}

const UNREACHABLE: Health = { status: "unreachable", checks: {} };

/** Turns the body of GET /api/health into a Health value, rejecting anything unexpected. */
export function parseHealth(body: unknown): Health {
  if (typeof body !== "object" || body === null) return UNREACHABLE;
  const { status, checks } = body as { status?: unknown; checks?: unknown };
  if (status !== "ok" && status !== "degraded") return UNREACHABLE;
  if (typeof checks !== "object" || checks === null) return UNREACHABLE;
  const parsed: Record<string, CheckState> = {};
  for (const [name, state] of Object.entries(checks)) {
    if (state !== "ok" && state !== "error") return UNREACHABLE;
    parsed[name] = state;
  }
  return { status, checks: parsed };
}

/** Server-side call to the API health check. Never throws. */
export async function fetchHealth(apiUrl: string): Promise<Health> {
  try {
    const response = await fetch(`${apiUrl}/api/health`, { cache: "no-store" });
    return parseHealth(await response.json());
  } catch {
    return UNREACHABLE;
  }
}
