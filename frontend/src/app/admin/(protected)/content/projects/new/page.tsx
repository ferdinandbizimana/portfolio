import { NEW_PROJECT } from "../project-draft";
import { ProjectForm } from "../project-form";

export const metadata = { title: "New project" };

export default function NewProjectPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">New project</h1>
      <ProjectForm id={null} initial={NEW_PROJECT} />
    </div>
  );
}
