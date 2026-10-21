import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/site";
import { fetchPortfolio, fetchPublicDashboards } from "@/lib/public-api";

export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = siteUrl();
  const pages = ["", "/about", "/experience", "/skills", "/projects", "/contact"];
  let projects: { slug: string }[] = [];
  let dashboards: { slug: string }[] = [];
  try {
    [projects, dashboards] = await Promise.all([
      fetchPortfolio().then((p) => p.projects),
      fetchPublicDashboards(),
    ]);
  } catch {
    // The sitemap still lists the main pages when the API is down.
  }
  return [
    ...pages.map((path) => ({ url: `${base}${path}` })),
    ...projects.map((p) => ({ url: `${base}/projects/${p.slug}` })),
    ...(dashboards.length ? [{ url: `${base}/dashboards` }] : []),
    ...dashboards.map((d) => ({ url: `${base}/dashboards/${d.slug}` })),
  ];
}
