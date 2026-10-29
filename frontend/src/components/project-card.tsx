import Image from "next/image";
import Link from "next/link";

import type { ProjectSummary } from "@/lib/portfolio";

export function ProjectCard({ project }: { project: ProjectSummary }) {
  return (
    <Link
      href={`/projects/${project.slug}`}
      className="group flex flex-col overflow-hidden rounded-xl border border-line bg-surface text-ink no-underline shadow-[0_1px_2px_rgba(16,24,40,0.04)] transition hover:-translate-y-0.5 hover:border-accent hover:shadow-md"
    >
      {project.cover ? (
        <Image
          src={project.cover.url}
          alt=""
          width={640}
          height={360}
          unoptimized
          className="aspect-video w-full object-cover"
        />
      ) : (
        <div
          aria-hidden
          className="flex aspect-video w-full items-end bg-gradient-to-br from-hero to-accent p-4"
        >
          <span className="text-sm font-semibold text-on-hero/90">
            {project.tags[0] ?? "Case study"}
          </span>
        </div>
      )}
      <div className="flex flex-1 flex-col gap-2 p-5">
        <h3 className="text-lg font-semibold group-hover:text-accent">{project.title}</h3>
        {project.summary && <p className="text-sm leading-relaxed text-muted">{project.summary}</p>}
        {project.tags.length > 0 && <Tags tags={project.tags} />}
        <span className="pt-1 text-sm font-medium text-accent">Read the case study →</span>
      </div>
    </Link>
  );
}

export function Tags({ tags }: { tags: string[] }) {
  return (
    <ul className="mt-auto flex flex-wrap gap-1.5 pt-2" aria-label="Tags">
      {tags.map((tag) => (
        <li
          key={tag}
          className="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-medium text-accent"
        >
          {tag}
        </li>
      ))}
    </ul>
  );
}
