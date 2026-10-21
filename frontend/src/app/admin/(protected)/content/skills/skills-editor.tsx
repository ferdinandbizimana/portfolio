"use client";

import { useState, type FormEvent } from "react";

import { Field, StatusMessage } from "@/components/admin/fields";
import { OrderedList } from "@/components/admin/ordered-list";
import { useSave } from "@/components/admin/use-save";
import { parseItems, type SkillGroup } from "@/lib/portfolio";

type Draft = { id: number | null; name: string; itemsText: string };

export function SkillsEditor({ groups }: { groups: SkillGroup[] }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const { save, pending, message } = useSave();

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    const body = { name: draft.name, items: parseItems(draft.itemsText) };
    const result = draft.id
      ? await save("PUT", `/api/admin/content/skills/${draft.id}`, body)
      : await save("POST", "/api/admin/content/skills", body);
    if (result.ok) setDraft(null);
  }

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <StatusMessage message={message} />
      {groups.length === 0 && !draft && <p className="text-muted">No skill groups yet.</p>}
      <OrderedList
        items={groups}
        disabled={pending}
        render={(g) => (
          <>
            <p className="font-medium">{g.name}</p>
            <p className="text-sm text-muted">{g.items.join(", ")}</p>
          </>
        )}
        onEdit={(g) => setDraft({ id: g.id, name: g.name, itemsText: g.items.join("\n") })}
        onDelete={(g) => {
          if (window.confirm(`Delete "${g.name}"?`))
            void save("DELETE", `/api/admin/content/skills/${g.id}`, undefined, "Deleted.");
        }}
        onMove={(ids) =>
          void save("POST", "/api/admin/content/skills/reorder", { ids }, "Order saved.")
        }
      />
      {draft ? (
        <form
          onSubmit={onSubmit}
          className="flex flex-col gap-4 rounded-lg border border-line p-4"
          aria-label={draft.id ? "Edit skill group" : "New skill group"}
        >
          <Field label="Group name" hint="For example: SAP S/4HANA, Analytics, Languages.">
            <input
              className="input"
              required
              maxLength={120}
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </Field>
          <Field label="Skills" hint="One per line.">
            <textarea
              className="input"
              rows={6}
              value={draft.itemsText}
              onChange={(e) => setDraft({ ...draft, itemsText: e.target.value })}
            />
          </Field>
          <div className="flex gap-2">
            <button type="submit" className="btn-primary" disabled={pending}>
              {pending ? "Saving…" : "Save group"}
            </button>
            <button type="button" className="btn-secondary" onClick={() => setDraft(null)}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          className="btn-primary self-start"
          onClick={() => setDraft({ id: null, name: "", itemsText: "" })}
        >
          Add a skill group
        </button>
      )}
    </div>
  );
}
