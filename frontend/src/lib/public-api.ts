import "server-only";

import { PORTFOLIO_TAG, type Portfolio, type Project } from "./portfolio";
import { API_URL } from "./server-api";

// Public data is cached by Next.js and refreshed when the admin saves a change
// (updateTag), or at the latest after REVALIDATE_SECONDS.
const REVALIDATE_SECONDS = 600;

export async function fetchPortfolio(): Promise<Portfolio> {
  const response = await fetch(`${API_URL}/api/public/portfolio`, {
    next: { revalidate: REVALIDATE_SECONDS, tags: [PORTFOLIO_TAG] },
  });
  if (!response.ok) throw new Error(`Portfolio could not be loaded (${response.status}).`);
  return (await response.json()) as Portfolio;
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
