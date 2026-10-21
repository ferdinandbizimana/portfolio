import Image from "next/image";
import Link from "next/link";

import type { ProjectSummary } from "@/lib/portfolio";

export function ProjectCard({ project }: { project: ProjectSummary }) {
  return (
    <Link
      href={`/projects/${project.slug}`}
      className="group flex flex-col overflow-hidden rounded-lg border border-line text-ink hover:bg-panel"
    >
      {project.cover && (
        <Image
          src={project.cover.url}
          alt=""
          width={640}
          height={360}
          unoptimized
          className="aspect-video w-full object-cover"
        />
      )}
      <div className="flex flex-1 flex-col gap-2 p-4">
        <h3 className="font-semibold group-hover:text-accent">{project.title}</h3>
        {project.summary && <p className="text-sm text-muted">{project.summary}</p>}
        {project.tags.length > 0 && <Tags tags={project.tags} />}
      </div>
    </Link>
  );
}

export function Tags({ tags }: { tags: string[] }) {
  return (
    <ul className="mt-auto flex flex-wrap gap-1.5" aria-label="Tags">
      {tags.map((tag) => (
        <li key={tag} className="rounded-full bg-panel px-2 py-0.5 text-xs text-muted">
          {tag}
        </li>
      ))}
    </ul>
  );
}
