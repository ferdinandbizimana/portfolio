"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { refreshPublicPages } from "@/app/admin/actions";
import { sendJson } from "@/lib/api-errors";
import { formatDateTime } from "@/lib/audit";
import {
  publicPath,
  sharePath,
  VISIBILITY_LABEL,
  type Publication,
  type Visibility,
} from "@/lib/publications";

export function PublicationList({ publications }: { publications: Publication[] }) {
  if (publications.length === 0) {
    return <p className="text-muted">Nothing is published yet.</p>;
  }
  return (
    <ul className="flex flex-col gap-4">
      {publications.map((p) => (
        <PublicationItem key={p.id} publication={p} />
      ))}
    </ul>
  );
}

function PublicationItem({ publication }: { publication: Publication }) {
  const router = useRouter();
  const selectId = useId();
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);

  async function act(
    method: "PATCH" | "POST" | "DELETE",
    path: string,
    body?: unknown,
  ): Promise<void> {
    setBusy(true);
    setError("");
    const result = await sendJson(method, path, body);
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    await refreshPublicPages();
    router.refresh();
  }

  const base = `/api/admin/publications/${publication.id}`;

  function changeVisibility(visibility: Visibility) {
    void act("PATCH", base, { visibility });
  }

  function renewLink() {
    if (!window.confirm("Create a new secret link? The current link will stop working.")) return;
    void act("POST", `${base}/new-link`);
  }

  function unpublish() {
    if (!window.confirm(`Unpublish "${publication.title}"? Its links will stop working.`)) return;
    void act("DELETE", base);
  }

  async function copyLink() {
    await navigator.clipboard.writeText(`${window.location.origin}${sharePath(publication)}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <li className="flex flex-col gap-3 rounded-lg border border-line p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="font-semibold">{publication.title}</h2>
          <p className="text-sm text-muted">
            {publication.detail_level === "summary" ? "Summary only" : "Full detail"}
            {publication.include_checks ? ", with self-checks" : ""} · created{" "}
            {formatDateTime(publication.created_at)}
            {publication.run_id !== null && (
              <>
                {" "}
                · from{" "}
                <Link href={`/admin/runs/${publication.run_id}`}>run #{publication.run_id}</Link>
              </>
            )}
          </p>
        </div>
        <button
          type="button"
          className="btn-secondary text-danger"
          onClick={unpublish}
          disabled={busy}
        >
          Unpublish
        </button>
      </div>

      <div className="flex flex-col gap-1 text-sm">
        <label htmlFor={selectId} className="font-medium">
          Who can see it
        </label>
        <select
          id={selectId}
          className="input max-w-md"
          value={publication.visibility}
          disabled={busy}
          onChange={(e) => changeVisibility(e.target.value as Visibility)}
        >
          {(Object.keys(VISIBILITY_LABEL) as Visibility[]).map((v) => (
            <option key={v} value={v}>
              {VISIBILITY_LABEL[v]}
            </option>
          ))}
        </select>
      </div>

      {publication.visibility !== "private" && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {publication.visibility === "public" && (
            <a
              href={publicPath(publication)}
              target="_blank"
              rel="noopener"
              className="btn-secondary"
            >
              Open public page
            </a>
          )}
          <a href={sharePath(publication)} target="_blank" rel="noopener" className="btn-secondary">
            Open shared link
          </a>
          <button type="button" className="btn-secondary" onClick={copyLink}>
            {copied ? "Copied" : "Copy shared link"}
          </button>
          <button type="button" className="btn-secondary" onClick={renewLink} disabled={busy}>
            New shared link
          </button>
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </li>
  );
}
