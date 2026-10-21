"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { StatusMessage } from "@/components/admin/fields";
import { sendJson } from "@/lib/api-errors";
import { formatDateTime } from "@/lib/audit";

export interface ReportTemplate {
  id: number;
  kind: "docx" | "pptx";
  name: string;
  filename: string;
  active: boolean;
  created_at: string;
}

export function TemplateManager({ templates }: { templates: ReportTemplate[] }) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  async function act(method: "POST" | "DELETE", path: string, okText: string) {
    const result = await sendJson(method, path);
    setMessage(result.ok ? { kind: "ok", text: okText } : { kind: "error", text: result.message });
    router.refresh();
  }

  async function upload(file: File) {
    const form = new FormData();
    form.append("file", file);
    const result = await sendJson<ReportTemplate>("POST", "/api/admin/templates", form);
    setMessage(
      result.ok
        ? { kind: "ok", text: `${file.name} uploaded. Make it active to use it.` }
        : { kind: "error", text: result.message },
    );
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      <button
        type="button"
        className="btn-primary self-start"
        onClick={() => input.current?.click()}
      >
        Upload a template
      </button>
      <input
        ref={input}
        type="file"
        accept=".docx,.dotx,.pptx,.potx"
        className="sr-only"
        aria-label="Choose a template"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void upload(file);
          e.target.value = "";
        }}
      />
      <StatusMessage message={message} />
      {templates.length === 0 ? (
        <p className="text-muted">No templates yet. Reports use a clean built-in layout.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {templates.map((t) => (
            <li
              key={t.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line p-3"
            >
              <div>
                <p className="font-medium">
                  {t.filename}{" "}
                  <span className="text-xs text-muted">
                    {t.kind === "docx" ? "Word" : "PowerPoint"} · {formatDateTime(t.created_at)}
                  </span>
                </p>
                {t.active && (
                  <span className="rounded-full bg-success-soft px-2 py-0.5 text-xs text-success">
                    Active
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                {t.active ? (
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() =>
                      act(
                        "POST",
                        `/api/admin/templates/${t.id}/deactivate`,
                        "Template no longer used.",
                      )
                    }
                  >
                    Stop using
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() =>
                      act(
                        "POST",
                        `/api/admin/templates/${t.id}/activate`,
                        "Template is now active.",
                      )
                    }
                  >
                    Make active
                  </button>
                )}
                <button
                  type="button"
                  className="btn-secondary text-danger"
                  onClick={() => {
                    if (window.confirm(`Delete ${t.filename}?`))
                      void act("DELETE", `/api/admin/templates/${t.id}`, "Template deleted.");
                  }}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
