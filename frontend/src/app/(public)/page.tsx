import Image from "next/image";
import Link from "next/link";

import { Markdown } from "@/components/markdown";
import { CredentialList } from "@/components/portfolio/credentials";
import { ProjectCard } from "@/components/project-card";
import { formatPeriod, initials, monthOf, yearsOfExperience } from "@/lib/portfolio";
import { fetchPortfolio, fetchPublicDashboards } from "@/lib/public-api";

export default async function HomePage() {
  const [{ profile, experience, skills, projects }, dashboards] = await Promise.all([
    fetchPortfolio(),
    fetchPublicDashboards(),
  ]);
  const featured = projects.filter((p) => p.featured);
  // Featured first, then the others, so the row is always full when there is enough work.
  const shown = [...featured, ...projects.filter((p) => !p.featured)].slice(0, 3);
  const years = yearsOfExperience(experience, monthOf(new Date()));
  const facts = [
    years > 0 ? `${years}+ years in supply chain` : "",
    profile.location,
    profile.languages.length ? profile.languages.join(" · ") : "",
  ].filter(Boolean);
  const credentials = [...profile.certifications, ...profile.education];
  // Structured data so search engines (and recruiters' tools) read the profile correctly.
  const person = {
    "@context": "https://schema.org",
    "@type": "Person",
    name: profile.full_name,
    jobTitle: profile.headline || undefined,
    address: profile.location
      ? { "@type": "PostalAddress", addressLocality: profile.location }
      : undefined,
    sameAs: [profile.linkedin_url, profile.github_url].filter(Boolean),
    knowsAbout: skills.flatMap((group) => group.items).slice(0, 30),
  };

  return (
    <div>
      <script
        type="application/ld+json"
        // JSON.stringify output with "<" escaped cannot close the script element.
        dangerouslySetInnerHTML={{ __html: JSON.stringify(person).replace(/</g, "\\u003c") }}
      />
      {/* Hero: who, what value, what next */}
      <section className="bg-hero text-on-hero">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-16 sm:py-20 md:grid-cols-[1fr_auto]">
          <div className="max-w-3xl">
            {profile.availability && (
              <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/25 px-3 py-1 text-sm">
                <span aria-hidden className="h-2 w-2 rounded-full bg-gold" />
                {profile.availability}
              </p>
            )}
            <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">{profile.full_name}</h1>
            {profile.headline && (
              <p className="mt-3 text-xl font-medium text-gold sm:text-2xl">{profile.headline}</p>
            )}
            {profile.summary_md && (
              <div className="mt-5 max-w-2xl text-lg leading-relaxed text-white/85 [&_a]:text-gold [&_strong]:text-white">
                <Markdown>{profile.summary_md}</Markdown>
              </div>
            )}
            <div className="mt-8 flex flex-wrap gap-3">
              {profile.cv && (
                <a href={profile.cv.url} className="btn-hero no-underline">
                  Download CV
                </a>
              )}
              <Link href="/contact" className="btn-ghost no-underline">
                Get in touch
              </Link>
              {projects.length > 0 && (
                <Link href="/projects" className="btn-ghost no-underline">
                  See case studies
                </Link>
              )}
            </div>
            {facts.length > 0 && (
              <ul
                className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-white/75"
                aria-label="At a glance"
              >
                {facts.map((fact) => (
                  <li key={fact} className="flex items-center gap-2">
                    <span aria-hidden className="h-1 w-1 rounded-full bg-gold" />
                    {fact}
                  </li>
                ))}
              </ul>
            )}
          </div>
          {!profile.photo && (
            <div
              aria-hidden
              className="hidden h-60 w-60 place-items-center rounded-2xl border border-white/15 bg-white/5 text-7xl font-bold tracking-tight text-gold md:grid"
            >
              {initials(profile.full_name)}
            </div>
          )}
          {profile.photo && (
            <Image
              src={profile.photo.url}
              alt={`Photo of ${profile.full_name}`}
              width={260}
              height={260}
              unoptimized
              priority
              className="h-44 w-44 rounded-2xl object-cover ring-4 ring-gold/80 sm:h-60 sm:w-60"
            />
          )}
        </div>
      </section>

      {/* Key results */}
      {profile.highlights.length > 0 && (
        <section aria-label="Key results" className="border-b border-line bg-panel">
          <dl
            className={`mx-auto grid max-w-6xl gap-px px-4 py-8 sm:grid-cols-2 ${
              profile.highlights.length >= 3 ? "lg:grid-cols-3" : ""
            } ${profile.highlights.length >= 4 ? "xl:grid-cols-4" : ""}`}
          >
            {profile.highlights.map((item) => (
              <div key={`${item.value}-${item.label}`} className="flex flex-col gap-1 px-4 py-3">
                <dt className="order-2 text-sm text-muted">{item.label}</dt>
                <dd className="order-1 text-4xl font-bold tracking-tight text-accent">
                  {item.value}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <div className="mx-auto flex max-w-6xl flex-col gap-20 px-4 py-16">
        {/* What I bring: from the skill groups */}
        {skills.length > 0 && (
          <section aria-labelledby="bring-heading">
            <p className="eyebrow mb-2">What I bring</p>
            <h2 id="bring-heading" className="section-title mb-8">
              From SAP data to decisions the business can act on
            </h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {skills.slice(0, 6).map((group) => (
                <div key={group.id} className="tile">
                  <h3 className="mb-3 font-semibold">{group.name}</h3>
                  <ul className="flex flex-wrap gap-1.5">
                    {group.items.slice(0, 8).map((item) => (
                      <li key={item} className="chip text-xs">
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Proof: case studies */}
        {shown.length > 0 && (
          <section aria-labelledby="projects-heading">
            <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="eyebrow mb-2">Selected work</p>
                <h2 id="projects-heading" className="section-title">
                  Case studies
                </h2>
              </div>
              <Link href="/projects" className="text-sm font-medium">
                All case studies →
              </Link>
            </div>
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {shown.map((project) => (
                <ProjectCard key={project.id} project={project} />
              ))}
            </div>
          </section>
        )}

        {/* Proof: live dashboards */}
        {dashboards.length > 0 && (
          <section
            aria-labelledby="dashboards-heading"
            className="rounded-2xl bg-accent-soft px-6 py-10 sm:px-10"
          >
            <p className="eyebrow mb-2">Live work</p>
            <h2 id="dashboards-heading" className="section-title mb-2">
              Explore my dashboards
            </h2>
            <p className="lead mb-6 max-w-2xl">
              Interactive dashboards built from SAP exports: filter them, search them, check the
              figures.
            </p>
            <ul className="grid gap-3 sm:grid-cols-3">
              {dashboards.slice(0, 3).map((d) => (
                <li key={d.slug}>
                  <Link
                    href={`/dashboards/${d.slug}`}
                    className="tile flex h-full flex-col gap-1 text-ink no-underline hover:border-accent"
                  >
                    <span className="font-semibold">{d.title}</span>
                    {d.description && <span className="text-sm text-muted">{d.description}</span>}
                    <span className="mt-auto pt-2 text-sm font-medium text-accent">Open →</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Career snapshot */}
        {experience.length > 0 && (
          <section aria-labelledby="career-heading">
            <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="eyebrow mb-2">Career</p>
                <h2 id="career-heading" className="section-title">
                  Experience
                </h2>
              </div>
              <Link href="/experience" className="text-sm font-medium">
                Full experience →
              </Link>
            </div>
            <ol className="grid gap-4 md:grid-cols-3">
              {experience.slice(0, 3).map((entry) => (
                <li key={entry.id} className="tile">
                  <p className="text-xs font-medium text-muted">
                    {formatPeriod(entry.start_month, entry.end_month)}
                  </p>
                  <p className="mt-1 font-semibold">{entry.role}</p>
                  <p className="text-sm text-muted">{entry.organisation}</p>
                </li>
              ))}
            </ol>
          </section>
        )}

        {credentials.length > 0 && (
          <section aria-labelledby="credentials-heading">
            <p className="eyebrow mb-2">Credentials</p>
            <h2 id="credentials-heading" className="section-title mb-8">
              Certifications and education
            </h2>
            <CredentialList items={credentials} />
          </section>
        )}

        {/* Close: one clear next step */}
        <section className="rounded-2xl bg-hero px-6 py-12 text-center text-on-hero sm:px-12">
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            Looking for someone who makes supply chain data work?
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-white/80">
            I am happy to talk about roles, projects and how better inventory data pays off.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <Link href="/contact" className="btn-hero no-underline">
              Contact me
            </Link>
            {profile.linkedin_url && (
              <a
                href={profile.linkedin_url}
                rel="me noopener"
                target="_blank"
                className="btn-ghost no-underline"
              >
                LinkedIn
              </a>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
