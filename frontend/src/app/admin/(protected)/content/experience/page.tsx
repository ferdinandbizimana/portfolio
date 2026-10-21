import type { Experience } from "@/lib/portfolio";
import { apiGet } from "@/lib/server-api";

import { ExperienceEditor } from "./experience-editor";

export const metadata = { title: "Experience" };

export default async function ExperienceAdminPage() {
  const response = await apiGet("/api/admin/content/experience");
  if (!response.ok) return <p role="alert">The experience list could not be loaded.</p>;
  const entries = (await response.json()) as Experience[];

  return (
    <div>
      <h1 className="mb-2 text-2xl font-semibold">Experience</h1>
      <p className="mb-6 text-muted">Roles shown on the Experience page, in this order.</p>
      <ExperienceEditor entries={entries} />
    </div>
  );
}
