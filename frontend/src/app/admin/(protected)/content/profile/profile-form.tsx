"use client";

import { useState, type FormEvent } from "react";

import { Field, FilePicker, MarkdownField, StatusMessage } from "@/components/admin/fields";
import { useSave } from "@/components/admin/use-save";
import type { Credential, Highlight, Profile } from "@/lib/portfolio";

export function ProfileForm({ initial }: { initial: Profile }) {
  const [profile, setProfile] = useState(initial);
  const { save, pending, message } = useSave();
  const set = <K extends keyof Profile>(key: K, value: Profile[K]) =>
    setProfile((p) => ({ ...p, [key]: value }));

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    await save("PUT", "/api/admin/content/profile", {
      full_name: profile.full_name,
      headline: profile.headline,
      location: profile.location,
      summary_md: profile.summary_md,
      about_md: profile.about_md,
      linkedin_url: profile.linkedin_url,
      github_url: profile.github_url,
      photo_file_id: profile.photo?.id ?? null,
      cv_file_id: profile.cv?.id ?? null,
      availability: profile.availability,
      highlights: profile.highlights.filter((h) => h.value.trim() && h.label.trim()),
      certifications: profile.certifications.filter((c) => c.title.trim()),
      education: profile.education.filter((c) => c.title.trim()),
      languages: profile.languages.map((l) => l.trim()).filter(Boolean),
    });
  }

  return (
    <form onSubmit={onSubmit} className="flex max-w-2xl flex-col gap-5">
      <Field label="Full name">
        <input
          className="input"
          required
          maxLength={120}
          value={profile.full_name}
          onChange={(e) => set("full_name", e.target.value)}
        />
      </Field>
      <Field label="Headline" hint="One line under your name on the home page.">
        <input
          className="input"
          maxLength={200}
          value={profile.headline}
          onChange={(e) => set("headline", e.target.value)}
        />
      </Field>
      <Field label="Location">
        <input
          className="input"
          maxLength={120}
          value={profile.location}
          onChange={(e) => set("location", e.target.value)}
        />
      </Field>
      <Field
        label="Availability"
        hint='Shown with a gold dot at the top of the home page, e.g. "Open to supply chain roles in East Africa". Leave empty to hide.'
      >
        <input
          className="input"
          maxLength={200}
          value={profile.availability}
          onChange={(e) => set("availability", e.target.value)}
        />
      </Field>
      <MarkdownField
        label="Short introduction (home page)"
        value={profile.summary_md}
        onChange={(v) => set("summary_md", v)}
        rows={4}
        maxLength={5000}
      />
      <MarkdownField
        label="About (about page)"
        value={profile.about_md}
        onChange={(v) => set("about_md", v)}
        rows={12}
        maxLength={30000}
      />
      <HighlightsEditor value={profile.highlights} onChange={(v) => set("highlights", v)} />
      <CredentialsEditor
        legend="Certifications"
        value={profile.certifications}
        onChange={(v) => set("certifications", v)}
        max={20}
      />
      <CredentialsEditor
        legend="Education"
        value={profile.education}
        onChange={(v) => set("education", v)}
        max={10}
      />
      <Field label="Languages" hint="One per line, e.g. English (fluent).">
        <textarea
          className="input"
          rows={3}
          value={profile.languages.join("\n")}
          onChange={(e) => set("languages", e.target.value.split("\n").slice(0, 10))}
        />
      </Field>
      <Field label="LinkedIn address" hint="Full address starting with https://, or empty.">
        <input
          className="input"
          type="url"
          value={profile.linkedin_url}
          onChange={(e) => set("linkedin_url", e.target.value)}
        />
      </Field>
      <Field label="GitHub address" hint="Full address starting with https://, or empty.">
        <input
          className="input"
          type="url"
          value={profile.github_url}
          onChange={(e) => set("github_url", e.target.value)}
        />
      </Field>
      <FilePicker
        label="Photo (PNG, JPEG or WebP)"
        accept="image/png,image/jpeg,image/webp"
        value={profile.photo}
        onChange={(f) => set("photo", f)}
      />
      <FilePicker
        label="CV (PDF)"
        accept="application/pdf"
        value={profile.cv}
        onChange={(f) => set("cv", f)}
      />
      <StatusMessage message={message} />
      <button type="submit" className="btn-primary self-start" disabled={pending}>
        {pending ? "Saving…" : "Save profile"}
      </button>
    </form>
  );
}

function HighlightsEditor({
  value,
  onChange,
}: {
  value: Highlight[];
  onChange: (value: Highlight[]) => void;
}) {
  const update = (index: number, change: Partial<Highlight>) =>
    onChange(value.map((item, i) => (i === index ? { ...item, ...change } : item)));
  return (
    <fieldset className="flex flex-col gap-3 rounded-lg border border-line p-4">
      <legend className="px-1 text-sm font-semibold">Key results (home page)</legend>
      <p className="text-xs text-muted">
        Up to 6 results you can stand behind, shown large on the home page: a figure and what it
        measures, e.g. &ldquo;99%&rdquo; and &ldquo;inventory record accuracy at year-end
        count&rdquo;.
      </p>
      {value.map((item, index) => (
        <div key={index} className="flex flex-wrap items-end gap-2">
          <Field label={`Result ${index + 1}: figure`}>
            <input
              className="input w-28"
              maxLength={24}
              value={item.value}
              onChange={(e) => update(index, { value: e.target.value })}
            />
          </Field>
          <Field label={`Result ${index + 1}: what it measures`}>
            <input
              className="input min-w-64"
              maxLength={90}
              value={item.label}
              onChange={(e) => update(index, { label: e.target.value })}
            />
          </Field>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => onChange(value.filter((_, i) => i !== index))}
          >
            Remove
          </button>
        </div>
      ))}
      {value.length < 6 && (
        <button
          type="button"
          className="btn-secondary self-start"
          onClick={() => onChange([...value, { value: "", label: "" }])}
        >
          Add a key result
        </button>
      )}
    </fieldset>
  );
}

function CredentialsEditor({
  legend,
  value,
  onChange,
  max,
}: {
  legend: string;
  value: Credential[];
  onChange: (value: Credential[]) => void;
  max: number;
}) {
  const update = (index: number, change: Partial<Credential>) =>
    onChange(value.map((item, i) => (i === index ? { ...item, ...change } : item)));
  return (
    <fieldset className="flex flex-col gap-3 rounded-lg border border-line p-4">
      <legend className="px-1 text-sm font-semibold">{legend}</legend>
      {value.map((item, index) => (
        <div key={index} className="flex flex-wrap items-end gap-2">
          <Field label={`${legend} ${index + 1}: title`}>
            <input
              className="input min-w-56"
              maxLength={160}
              value={item.title}
              onChange={(e) => update(index, { title: e.target.value })}
            />
          </Field>
          <Field label="Issued by">
            <input
              className="input min-w-40"
              maxLength={160}
              value={item.issuer}
              onChange={(e) => update(index, { issuer: e.target.value })}
            />
          </Field>
          <Field label="Year">
            <input
              className="input w-24"
              maxLength={20}
              value={item.year}
              onChange={(e) => update(index, { year: e.target.value })}
            />
          </Field>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => onChange(value.filter((_, i) => i !== index))}
          >
            Remove
          </button>
        </div>
      ))}
      {value.length < max && (
        <button
          type="button"
          className="btn-secondary self-start"
          onClick={() => onChange([...value, { title: "", issuer: "", year: "" }])}
        >
          Add
        </button>
      )}
    </fieldset>
  );
}
