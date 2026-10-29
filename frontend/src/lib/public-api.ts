import "server-only";

import { PORTFOLIO_TAG, withProfileDefaults, type Portfolio, type Project } from "./portfolio";
import type { PublicDashboard, PublicListItem } from "./publications";
import { API_URL } from "./server-api";

// Public data is cached by Next.js and refreshed when the admin saves a change
// (updateTag), or at the latest after REVALIDATE_SECONDS.
const REVALIDATE_SECONDS = 600;

export async function fetchPortfolio(): Promise<Portfolio> {
  const response = await fetch(`${API_URL}/api/public/portfolio`, {
    next: { revalidate: REVALIDATE_SECONDS, tags: [PORTFOLIO_TAG] },
  });
  if (!response.ok) throw new Error(`Portfolio could not be loaded (${response.status}).`);
  return withProfileDefaults((await response.json()) as Portfolio);
}

/** A published project, or null if there is none with this slug. */
export async function fetchProject(slug: string): Promise<Project | null> {
  const response = await fetch(`${API_URL}/api/public/projects/${encodeURIComponent(slug)}`, {
    next: { revalidate: REVALIDATE_SECONDS, tags: [PORTFOLIO_TAG] },
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Project could not be loaded (${response.status}).`);
  return (await response.json()) as Project;
}

/** Dashboards listed on the public Dashboards page. */
export async function fetchPublicDashboards(): Promise<PublicListItem[]> {
  const response = await fetch(`${API_URL}/api/public/dashboards`, {
    next: { revalidate: REVALIDATE_SECONDS, tags: [PORTFOLIO_TAG] },
  });
  if (!response.ok) throw new Error(`Dashboards could not be loaded (${response.status}).`);
  return (await response.json()) as PublicListItem[];
}

/** A public dashboard, or null if it is not (or no longer) public. */
export async function fetchPublicDashboard(slug: string): Promise<PublicDashboard | null> {
  const response = await fetch(`${API_URL}/api/public/dashboards/${encodeURIComponent(slug)}`, {
    next: { revalidate: REVALIDATE_SECONDS, tags: [PORTFOLIO_TAG] },
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Dashboard could not be loaded (${response.status}).`);
  return (await response.json()) as PublicDashboard;
}

/** A dashboard shared by secret link. Never cached, so revoking a link works at once. */
export async function fetchSharedDashboard(token: string): Promise<PublicDashboard | null> {
  const response = await fetch(`${API_URL}/api/public/shared/${encodeURIComponent(token)}`, {
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Dashboard could not be loaded (${response.status}).`);
  return (await response.json()) as PublicDashboard;
}
