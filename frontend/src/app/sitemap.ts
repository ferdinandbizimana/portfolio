import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/site";
import { fetchPortfolio } from "@/lib/public-api";

export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = siteUrl();
  const pages = ["", "/about", "/experience", "/skills", "/projects", "/contact"];
  let projects: { slug: string }[] = [];
  try {
    projects = (await fetchPortfolio()).projects;
  } catch {
    // The sitemap still lists the main pages when the API is down.
  }
  return [
    ...pages.map((path) => ({ url: `${base}${path}` })),
    ...projects.map((p) => ({ url: `${base}/projects/${p.slug}` })),
  ];
}
