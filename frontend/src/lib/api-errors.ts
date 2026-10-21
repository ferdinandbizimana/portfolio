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

export type ApiResult<T = unknown> =
  { ok: true; data: T } | { ok: false; status: number; message: string };

/** Send a request from the browser to the API on the same origin. */
export async function sendJson<T = unknown>(
  method: "POST" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
): Promise<ApiResult<T>> {
  const init: RequestInit = { method, credentials: "same-origin" };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    return {
      ok: false,
      status: 0,
      message: "The server cannot be reached. Check your connection.",
    };
  }
  const data: unknown = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) return { ok: false, status: response.status, message: errorMessage(data) };
  return { ok: true, data: data as T };
}

export function postJson<T = unknown>(path: string, body?: unknown): Promise<ApiResult<T>> {
  return sendJson<T>("POST", path, body);
}
