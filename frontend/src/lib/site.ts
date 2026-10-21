/** Public address of the site, for absolute links (sitemap, social previews). */
export function siteUrl(): string {
  return (process.env.SITE_URL ?? "http://localhost:8080").replace(/\/+$/, "");
}
