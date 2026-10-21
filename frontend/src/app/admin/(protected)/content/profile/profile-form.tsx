"use client";

import { useState, type FormEvent } from "react";

import { Field, FilePicker, MarkdownField, StatusMessage } from "@/components/admin/fields";
import { useSave } from "@/components/admin/use-save";
import type { Profile } from "@/lib/portfolio";

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
