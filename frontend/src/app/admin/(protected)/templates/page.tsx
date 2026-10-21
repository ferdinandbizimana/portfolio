import { apiGet } from "@/lib/server-api";

import { TemplateManager, type ReportTemplate } from "./template-manager";

export const metadata = { title: "Report templates" };

export default async function TemplatesPage() {
  const response = await apiGet("/api/admin/templates");
  if (!response.ok) return <p role="alert">The templates could not be loaded.</p>;
  const templates = (await response.json()) as ReportTemplate[];

  return (
    <div className="max-w-3xl">
      <h1 className="mb-2 text-2xl font-semibold">Report templates</h1>
      <p className="mb-4 text-muted">
        Upload your organisation&apos;s Word and PowerPoint templates. The active template of each
        kind is used for every report generated from then on.
      </p>
      <div className="mb-6 rounded-lg bg-panel p-4 text-sm">
        <p className="mb-2 font-semibold">How to prepare a template</p>
        <ul className="list-disc pl-5">
          <li>
            Word: keep your cover, logo, header and footer. Where the report should go, put a
            paragraph containing only <code>{"{{p body }}"}</code>. You may also use{" "}
            <code>{"{{ title }}"}</code>, <code>{"{{ subtitle }}"}</code> and{" "}
            <code>{"{{ report_date }}"}</code> anywhere, for example on the cover.
          </li>
          <li>
            PowerPoint: the layouts called &quot;Title Slide&quot;, &quot;Title and Content&quot;
            and &quot;Title Only&quot; are used. The template&apos;s own example slides are left
            out.
          </li>
        </ul>
      </div>
      <TemplateManager templates={templates} />
    </div>
  );
}
