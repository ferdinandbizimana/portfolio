import Link from "next/link";
import type { ReactNode } from "react";

import { fetchPortfolio, fetchPublicDashboards } from "@/lib/public-api";

import { SiteNav } from "./site-nav";

// Rendered on request (never at build time, when the API is not running);
// the API responses themselves are cached (see lib/public-api.ts).
export const dynamic = "force-dynamic";

export default async function PublicLayout({ children }: { children: ReactNode }) {
  const [{ profile, projects }, dashboards] = await Promise.all([
    fetchPortfolio(),
    fetchPublicDashboards(),
  ]);
  const links = [
    { href: "/", label: "Home" },
    { href: "/about", label: "About" },
    { href: "/experience", label: "Experience" },
    { href: "/skills", label: "Skills" },
    ...(projects.length ? [{ href: "/projects", label: "Projects" }] : []),
    ...(dashboards.length ? [{ href: "/dashboards", label: "Dashboards" }] : []),
    { href: "/contact", label: "Contact" },
  ];

  return (
    <div className="flex min-h-screen flex-col">
      <a href="#content" className="skip-link">
        Skip to content
      </a>
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <Link href="/" className="text-lg font-semibold text-ink">
            {profile.full_name}
          </Link>
          <SiteNav links={links} />
        </div>
      </header>
      <main id="content" className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
        {children}
      </main>
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-4 gap-y-1 px-4 py-6 text-sm text-muted">
          <span>© {profile.full_name}</span>
          {profile.linkedin_url && (
            <a href={profile.linkedin_url} rel="me noopener" target="_blank">
              LinkedIn
            </a>
          )}
          {profile.github_url && (
            <a href={profile.github_url} rel="me noopener" target="_blank">
              GitHub
            </a>
          )}
          {profile.cv && <a href={profile.cv.url}>Download CV</a>}
        </div>
      </footer>
    </div>
  );
}
