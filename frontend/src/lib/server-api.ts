import "server-only";

import { cookies } from "next/headers";

export const API_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Server-side call to the API, forwarding the visitor's session cookie. */
export async function apiGet(path: string): Promise<Response> {
  const cookieHeader = (await cookies()).toString();
  return fetch(`${API_URL}${path}`, {
    cache: "no-store",
    headers: cookieHeader ? { cookie: cookieHeader } : undefined,
  });
}

export interface CurrentUser {
  email: string;
  last_login_at: string | null;
}

/** The logged-in admin, or null when there is no valid session. */
export async function getCurrentUser(): Promise<CurrentUser | null> {
  try {
    const response = await apiGet("/api/auth/me");
    if (!response.ok) return null;
    return (await response.json()) as CurrentUser;
  } catch {
    return null;
  }
}
