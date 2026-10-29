import type { Metadata } from "next";

import { PageShell } from "@/components/portfolio/page-shell";
import { ProjectCard } from "@/components/project-card";
import { fetchPortfolio } from "@/lib/public-api";

export const metadata: Metadata = { title: "Case studies" };

export default async function ProjectsPage() {
  const { projects } = await fetchPortfolio();

  return (
    <PageShell
      eyebrow="Selected work"
      title="Case studies"
      intro="Each one starts from a real supply chain problem: what was wrong, what I built, and what changed."
    >
      {projects.length === 0 ? (
        <p className="text-muted">More to come soon.</p>
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}
    </PageShell>
  );
}
