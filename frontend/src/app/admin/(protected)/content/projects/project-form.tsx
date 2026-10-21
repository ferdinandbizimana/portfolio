"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Field, FilePicker, MarkdownField, StatusMessage } from "@/components/admin/fields";
import { useSave } from "@/components/admin/use-save";
import { parseItems, slugify, type Project } from "@/lib/portfolio";

import type { ProjectDraft } from "./project-draft";

export function ProjectForm({ id, initial }: { id: number | null; initial: ProjectDraft }) {
  const router = useRouter();
  const [draft, setDraft] = useState(initial);
  const [slugTouched, setSlugTouched] = useState(id !== null);
  const { save, pending, message } = useSave();
  const set = <K extends keyof ProjectDraft>(key: K, value: ProjectDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const body = {
      slug: draft.slug,
      title: draft.title,
      summary: draft.summary,
      body_md: draft.body_md,
      tags: parseItems(draft.tagsText),
      cover_file_id: draft.cover?.id ?? null,
      published: draft.published,
      featured: draft.featured,
    };
    const result = id
      ? await save<Project>("PUT", `/api/admin/content/projects/${id}`, body)
      : await save<Project>("POST", "/api/admin/content/projects", body);
    if (result.ok && !id) router.replace(`/admin/content/projects/${result.data.id}`);
  }

  return (
    <form onSubmit={onSubmit} className="flex max-w-3xl flex-col gap-5">
      <Field label="Title">
        <input
          className="input"
          required
          maxLength={200}
          value={draft.title}
          onChange={(e) => {
            const title = e.target.value;
            setDraft((d) => ({ ...d, title, slug: slugTouched ? d.slug : slugify(title) }));
          }}
        />
      </Field>
      <Field label="Address" hint={`The page will be at /projects/${draft.slug || "…"}`}>
        <input
          className="input"
          required
          maxLength={120}
          pattern="[a-z0-9]+(-[a-z0-9]+)*"
          value={draft.slug}
          onChange={(e) => {
            setSlugTouched(true);
            set("slug", e.target.value);
          }}
        />
      </Field>
      <Field label="Summary" hint="One or two sentences for the project card.">
        <textarea
          className="input"
          rows={2}
          maxLength={500}
          value={draft.summary}
          onChange={(e) => set("summary", e.target.value)}
        />
      </Field>
      <Field label="Tags" hint="Separated by commas, e.g. SAP MM, EWM, Python.">
        <input
          className="input"
          value={draft.tagsText}
          onChange={(e) => set("tagsText", e.target.value)}
        />
      </Field>
      <FilePicker
        label="Cover image"
        accept="image/png,image/jpeg,image/webp"
        value={draft.cover}
        onChange={(f) => set("cover", f)}
      />
      <MarkdownField
        label="Case study"
        value={draft.body_md}
        onChange={(v) => set("body_md", v)}
        rows={18}
        maxLength={100000}
      />
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={draft.published}
          onChange={(e) => set("published", e.target.checked)}
        />
        Published (visible on the public site)
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={draft.featured}
          onChange={(e) => set("featured", e.target.checked)}
        />
        Featured on the home page
      </label>
      <StatusMessage message={message} />
      <div className="flex flex-wrap gap-2">
        <button type="submit" className="btn-primary" disabled={pending}>
          {pending ? "Saving…" : "Save project"}
        </button>
        <Link href="/admin/content/projects" className="btn-secondary">
          Back to projects
        </Link>
        {id && draft.published && (
          <Link href={`/projects/${draft.slug}`} className="btn-secondary" target="_blank">
            View on site
          </Link>
        )}
      </div>
    </form>
  );
}
