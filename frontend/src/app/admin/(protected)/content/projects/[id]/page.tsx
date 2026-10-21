import { notFound } from "next/navigation";

import type { Project } from "@/lib/portfolio";
import { apiGet } from "@/lib/server-api";

import { draftFrom } from "../project-draft";
import { ProjectForm } from "../project-form";

export const metadata = { title: "Edit project" };

export default async function EditProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const id = Number((await params).id);
  if (!Number.isInteger(id)) notFound();
  const response = await apiGet(`/api/admin/content/projects/${id}`);
  if (response.status === 404) notFound();
  if (!response.ok) return <p role="alert">The project could not be loaded.</p>;
  const project = (await response.json()) as Project;

  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Edit project</h1>
      <ProjectForm id={project.id} initial={draftFrom(project)} />
    </div>
  );
}
