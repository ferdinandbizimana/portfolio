/** Turns an API error body into one sentence for the user. */
export function errorMessage(
  body: unknown,
  fallback = "Something went wrong. Please try again.",
): string {
  if (typeof body !== "object" || body === null) return fallback;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  // FastAPI validation errors: [{ loc: [...], msg: "..." }, ...]
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { loc?: unknown; msg?: unknown };
    const field = Array.isArray(first.loc) ? String(first.loc[first.loc.length - 1]) : "";
    if (typeof first.msg === "string") return field ? `${field}: ${first.msg}` : first.msg;
  }
  return fallback;
}

/** POST JSON from the browser to the API on the same origin. */
export async function postJson(
  path: string,
  body?: unknown,
): Promise<{ ok: true; data: unknown } | { ok: false; status: number; message: string }> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    return {
      ok: false,
      status: 0,
      message: "The server cannot be reached. Check your connection.",
    };
  }
  const data: unknown = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) return { ok: false, status: response.status, message: errorMessage(data) };
  return { ok: true, data };
}
