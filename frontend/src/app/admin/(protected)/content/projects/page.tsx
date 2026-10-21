import Link from "next/link";

import type { ProjectSummary } from "@/lib/portfolio";
import { apiGet } from "@/lib/server-api";

import { ProjectOrder } from "./project-order";

export const metadata = { title: "Projects" };

export default async function ProjectsAdminPage() {
  const response = await apiGet("/api/admin/content/projects");
  if (!response.ok) return <p role="alert">The projects could not be loaded.</p>;
  const projects = (await response.json()) as ProjectSummary[];

  return (
    <div className="max-w-3xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="mb-1 text-2xl font-semibold">Projects and case studies</h1>
          <p className="text-muted">Only published projects appear on the public site.</p>
        </div>
        <Link href="/admin/content/projects/new" className="btn-primary">
          New project
        </Link>
      </div>
      {projects.length === 0 ? (
        <p className="text-muted">No projects yet.</p>
      ) : (
        <ProjectOrder projects={projects} />
      )}
    </div>
  );
}
