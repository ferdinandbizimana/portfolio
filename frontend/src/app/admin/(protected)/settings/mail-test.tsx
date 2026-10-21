"use client";

import { useState } from "react";

import { StatusMessage } from "@/components/admin/fields";
import { postJson } from "@/lib/api-errors";

export function MailTest() {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  async function onClick() {
    setPending(true);
    const result = await postJson("/api/admin/mail/test");
    setPending(false);
    setMessage(
      result.ok
        ? { kind: "ok", text: "Test e-mail sent. Check your inbox (and the spam folder)." }
        : { kind: "error", text: result.message },
    );
  }

  return (
    <div className="flex flex-col items-start gap-3">
      <button type="button" className="btn-secondary" onClick={onClick} disabled={pending}>
        {pending ? "Sending…" : "Send a test e-mail"}
      </button>
      <StatusMessage message={message} />
    </div>
  );
}
