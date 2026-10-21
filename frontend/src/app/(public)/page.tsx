import Image from "next/image";
import Link from "next/link";

import { Markdown } from "@/components/markdown";
import { ProjectCard } from "@/components/project-card";
import { formatPeriod } from "@/lib/portfolio";
import { fetchPortfolio } from "@/lib/public-api";

export default async function HomePage() {
  const { profile, experience, projects } = await fetchPortfolio();
  const featured = projects.filter((p) => p.featured);
  const shown = (featured.length ? featured : projects).slice(0, 3);
  const current = experience.find((e) => e.end_month === null) ?? experience[0];

  return (
    <div className="flex flex-col gap-16">
      <section className="flex flex-col-reverse items-start gap-8 sm:flex-row sm:items-center">
        <div className="flex-1">
          <h1 className="mb-2 text-3xl font-semibold sm:text-4xl">{profile.full_name}</h1>
          {profile.headline && <p className="mb-1 text-lg text-muted">{profile.headline}</p>}
          {profile.location && <p className="mb-4 text-sm text-muted">{profile.location}</p>}
          {profile.summary_md && <Markdown>{profile.summary_md}</Markdown>}
          <div className="mt-6 flex flex-wrap gap-3">
            <Link href="/contact" className="btn-primary">
              Get in touch
            </Link>
            {profile.cv && (
              <a href={profile.cv.url} className="btn-secondary">
                Download CV
              </a>
            )}
          </div>
        </div>
        {profile.photo && (
          <Image
            src={profile.photo.url}
            alt={`Photo of ${profile.full_name}`}
            width={200}
            height={200}
            unoptimized
            priority
            className="h-40 w-40 rounded-full object-cover sm:h-48 sm:w-48"
          />
        )}
      </section>

      {current && (
        <section aria-labelledby="now-heading">
          <h2
            id="now-heading"
            className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted"
          >
            {current.end_month ? "Most recent role" : "Currently"}
          </h2>
          <p className="text-lg">
            {current.role} · {current.organisation}
          </p>
          <p className="text-sm text-muted">
            {formatPeriod(current.start_month, current.end_month)}
          </p>
          <Link href="/experience" className="mt-2 inline-block text-sm">
            Full experience →
          </Link>
        </section>
      )}

      {shown.length > 0 && (
        <section aria-labelledby="projects-heading">
          <div className="mb-4 flex items-baseline justify-between">
            <h2 id="projects-heading" className="text-xl font-semibold">
              {featured.length ? "Featured work" : "Projects"}
            </h2>
            <Link href="/projects" className="text-sm">
              All projects →
            </Link>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {shown.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
