import type { FileRef, Project } from "@/lib/portfolio";

/** The project form's state (shared by the server pages and the client form). */
export type ProjectDraft = {
  slug: string;
  title: string;
  summary: string;
  body_md: string;
  tagsText: string;
  cover: FileRef | null;
  published: boolean;
  featured: boolean;
};

export const NEW_PROJECT: ProjectDraft = {
  slug: "",
  title: "",
  summary: "",
  body_md: "",
  tagsText: "",
  cover: null,
  published: false,
  featured: false,
};

export function draftFrom(project: Project): ProjectDraft {
  return { ...project, tagsText: project.tags.join(", ") };
}
