import type { Metadata } from "next";

import { ProjectCard } from "@/components/project-card";
import { fetchPortfolio } from "@/lib/public-api";

export const metadata: Metadata = { title: "Projects and case studies" };

export default async function ProjectsPage() {
  const { projects } = await fetchPortfolio();

  return (
    <div>
      <h1 className="mb-8 text-3xl font-semibold">Projects and case studies</h1>
      {projects.length === 0 ? (
        <p className="text-muted">More to come soon.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}
    </div>
  );
}
