import type { Dashboard } from "./dashboard";

export type Visibility = "private" | "secret" | "public";

export interface Publication {
  id: number;
  run_id: number | null;
  slug: string;
  secret_token: string;
  visibility: Visibility;
  title: string;
  description: string;
  detail_level: "summary" | "detail";
  include_checks: boolean;
  snapshot: Dashboard;
  created_at: string;
  published_at: string | null;
}

export interface PublicDashboard {
  slug: string;
  title: string;
  description: string;
  published_at: string | null;
  dashboard: Dashboard;
}

export type PublicListItem = Omit<PublicDashboard, "dashboard">;

export const VISIBILITY_LABEL: Record<Visibility, string> = {
  private: "Private (only you)",
  secret: "Secret link (anyone with the link)",
  public: "Public (listed on the Dashboards page)",
};

export function sharePath(publication: Pick<Publication, "secret_token">): string {
  return `/d/${publication.secret_token}`;
}

export function publicPath(publication: Pick<Publication, "slug">): string {
  return `/dashboards/${publication.slug}`;
}
