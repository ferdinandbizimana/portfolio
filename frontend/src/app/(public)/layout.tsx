import Link from "next/link";
import type { ReactNode } from "react";

import { initials } from "@/lib/portfolio";
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
    ...(projects.length ? [{ href: "/projects", label: "Case studies" }] : []),
    ...(dashboards.length ? [{ href: "/dashboards", label: "Dashboards" }] : []),
    { href: "/contact", label: "Contact" },
  ];

  return (
    <div className="flex min-h-screen flex-col">
      <a href="#content" className="skip-link">
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b border-line bg-surface/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-3 md:flex-row md:items-center md:justify-between">
          <Link href="/" className="flex items-center gap-3 text-ink">
            <span
              aria-hidden
              className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-hero text-sm font-bold text-on-hero"
            >
              {initials(profile.full_name)}
            </span>
            <span className="font-semibold">{profile.full_name}</span>
          </Link>
          <div className="flex items-center gap-3">
            <SiteNav links={links} />
            <Link
              href="/contact"
              className="btn-primary hidden whitespace-nowrap no-underline lg:inline-block"
            >
              Contact me
            </Link>
          </div>
        </div>
      </header>
      <main id="content" className="flex-1">
        {children}
      </main>
      <footer className="border-t border-line bg-panel">
        <div className="mx-auto grid max-w-6xl gap-6 px-4 py-10 text-sm sm:grid-cols-[2fr_1fr]">
          <div>
            <p className="font-semibold text-ink">{profile.full_name}</p>
            {profile.location && <p className="mt-1 text-muted">{profile.location}</p>}
          </div>
          <ul className="flex flex-col gap-1.5" aria-label="Links">
            <li>
              <Link href="/contact">Send me a message</Link>
            </li>
            {profile.linkedin_url && (
              <li>
                <a href={profile.linkedin_url} rel="me noopener" target="_blank">
                  LinkedIn
                </a>
              </li>
            )}
            {profile.github_url && (
              <li>
                <a href={profile.github_url} rel="me noopener" target="_blank">
                  GitHub
                </a>
              </li>
            )}
            {profile.cv && (
              <li>
                <a href={profile.cv.url}>Download CV</a>
              </li>
            )}
          </ul>
        </div>
        <p className="mx-auto max-w-6xl px-4 pb-8 text-xs text-muted">© {profile.full_name}</p>
      </footer>
    </div>
  );
}
