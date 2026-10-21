"use client";

import { useRouter } from "next/navigation";

import { StatusMessage } from "@/components/admin/fields";
import { OrderedList } from "@/components/admin/ordered-list";
import { useSave } from "@/components/admin/use-save";
import type { ProjectSummary } from "@/lib/portfolio";

export function ProjectOrder({ projects }: { projects: ProjectSummary[] }) {
  const router = useRouter();
  const { save, pending, message } = useSave();

  return (
    <div className="flex flex-col gap-4">
      <StatusMessage message={message} />
      <OrderedList
        items={projects}
        disabled={pending}
        render={(p) => (
          <>
            <p className="font-medium">
              {p.title}{" "}
              <span
                className={`ml-1 rounded-full px-2 py-0.5 text-xs ${
                  p.published ? "bg-success-soft text-success" : "bg-panel text-muted"
                }`}
              >
                {p.published ? "Published" : "Draft"}
              </span>
              {p.featured && (
                <span className="ml-1 rounded-full bg-panel px-2 py-0.5 text-xs text-muted">
                  Featured
                </span>
              )}
            </p>
            <p className="text-sm text-muted">/projects/{p.slug}</p>
          </>
        )}
        onEdit={(p) => router.push(`/admin/content/projects/${p.id}`)}
        onDelete={(p) => {
          if (window.confirm(`Delete "${p.title}"? This cannot be undone.`))
            void save("DELETE", `/api/admin/content/projects/${p.id}`, undefined, "Deleted.");
        }}
        onMove={(ids) =>
          void save("POST", "/api/admin/content/projects/reorder", { ids }, "Order saved.")
        }
      />
    </div>
  );
}
