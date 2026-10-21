import type { SkillGroup } from "@/lib/portfolio";
import { apiGet } from "@/lib/server-api";

import { SkillsEditor } from "./skills-editor";

export const metadata = { title: "Skills" };

export default async function SkillsAdminPage() {
  const response = await apiGet("/api/admin/content/skills");
  if (!response.ok) return <p role="alert">The skills could not be loaded.</p>;
  const groups = (await response.json()) as SkillGroup[];

  return (
    <div>
      <h1 className="mb-2 text-2xl font-semibold">Skills</h1>
      <p className="mb-6 text-muted">Groups of skills shown on the Skills page, in this order.</p>
      <SkillsEditor groups={groups} />
    </div>
  );
}
