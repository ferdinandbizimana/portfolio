"use client";

import { useState, type FormEvent } from "react";

import { Field, MarkdownField, StatusMessage } from "@/components/admin/fields";
import { OrderedList } from "@/components/admin/ordered-list";
import { useSave } from "@/components/admin/use-save";
import { formatPeriod, type Experience } from "@/lib/portfolio";

type Draft = Omit<Experience, "id"> & { id: number | null };

const EMPTY: Draft = {
  id: null,
  role: "",
  organisation: "",
  location: "",
  start_month: "",
  end_month: null,
  description_md: "",
};

export function ExperienceEditor({ entries }: { entries: Experience[] }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const { save, pending, message } = useSave();

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    const { id, ...body } = draft;
    const result = id
      ? await save("PUT", `/api/admin/content/experience/${id}`, body)
      : await save("POST", "/api/admin/content/experience", body);
    if (result.ok) setDraft(null);
  }

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <StatusMessage message={message} />
      {entries.length === 0 && !draft && <p className="text-muted">No roles yet.</p>}
      <OrderedList
        items={entries}
        disabled={pending}
        render={(e) => (
          <>
            <p className="font-medium">
              {e.role} · {e.organisation}
            </p>
            <p className="text-sm text-muted">{formatPeriod(e.start_month, e.end_month)}</p>
          </>
        )}
        onEdit={(e) => setDraft({ ...e })}
        onDelete={(e) => {
          if (window.confirm(`Delete "${e.role}"?`))
            void save("DELETE", `/api/admin/content/experience/${e.id}`, undefined, "Deleted.");
        }}
        onMove={(ids) =>
          void save("POST", "/api/admin/content/experience/reorder", { ids }, "Order saved.")
        }
      />
      {draft ? (
        <form
          onSubmit={onSubmit}
          className="flex flex-col gap-4 rounded-lg border border-line p-4"
          aria-label={draft.id ? "Edit role" : "New role"}
        >
          <h2 className="font-semibold">{draft.id ? "Edit role" : "New role"}</h2>
          <Field label="Role">
            <input
              className="input"
              required
              maxLength={200}
              value={draft.role}
              onChange={(e) => setDraft({ ...draft, role: e.target.value })}
            />
          </Field>
          <Field label="Organisation">
            <input
              className="input"
              required
              maxLength={200}
              value={draft.organisation}
              onChange={(e) => setDraft({ ...draft, organisation: e.target.value })}
            />
          </Field>
          <Field label="Location">
            <input
              className="input"
              maxLength={120}
              value={draft.location}
              onChange={(e) => setDraft({ ...draft, location: e.target.value })}
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Start month">
              <input
                className="input"
                type="month"
                required
                value={draft.start_month}
                onChange={(e) => setDraft({ ...draft, start_month: e.target.value })}
              />
            </Field>
            <Field label="End month" hint="Leave empty for your current role.">
              <input
                className="input"
                type="month"
                value={draft.end_month ?? ""}
                onChange={(e) => setDraft({ ...draft, end_month: e.target.value || null })}
              />
            </Field>
          </div>
          <MarkdownField
            label="What you did"
            value={draft.description_md}
            onChange={(v) => setDraft({ ...draft, description_md: v })}
            maxLength={10000}
          />
          <div className="flex gap-2">
            <button type="submit" className="btn-primary" disabled={pending}>
              {pending ? "Saving…" : "Save role"}
            </button>
            <button type="button" className="btn-secondary" onClick={() => setDraft(null)}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button type="button" className="btn-primary self-start" onClick={() => setDraft(EMPTY)}>
          Add a role
        </button>
      )}
    </div>
  );
}
