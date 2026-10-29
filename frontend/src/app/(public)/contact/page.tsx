import type { Metadata } from "next";

import { PageShell } from "@/components/portfolio/page-shell";
import { fetchPortfolio } from "@/lib/public-api";

import { ContactForm } from "./contact-form";

export const metadata: Metadata = { title: "Contact" };

export default async function ContactPage() {
  const { profile } = await fetchPortfolio();

  return (
    <PageShell
      eyebrow="Contact"
      title="Let's talk"
      intro="About a role, a project or your supply chain data. I reply by e-mail as soon as I can."
    >
      <div className="grid gap-10 lg:grid-cols-[1fr_320px]">
        <div className="tile max-w-2xl">
          <ContactForm />
        </div>
        <aside className="flex flex-col gap-4 text-sm">
          {profile.availability && (
            <p className="tile flex items-center gap-2">
              <span aria-hidden className="h-2 w-2 shrink-0 rounded-full bg-gold" />
              {profile.availability}
            </p>
          )}
          {profile.location && (
            <div className="tile">
              <p className="text-xs font-semibold tracking-wide text-muted uppercase">Based in</p>
              <p className="mt-1">{profile.location}</p>
            </div>
          )}
          {(profile.linkedin_url || profile.cv) && (
            <div className="tile flex flex-col gap-2">
              {profile.linkedin_url && (
                <a href={profile.linkedin_url} rel="me noopener" target="_blank">
                  LinkedIn profile
                </a>
              )}
              {profile.cv && <a href={profile.cv.url}>Download CV (PDF)</a>}
            </div>
          )}
        </aside>
      </div>
    </PageShell>
  );
}
