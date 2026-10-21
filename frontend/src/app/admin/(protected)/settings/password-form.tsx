"use client";

import { useState, type FormEvent } from "react";

import { postJson } from "@/lib/api-errors";

export function PasswordForm() {
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const newPassword = String(form.get("new_password") ?? "");
    if (newPassword !== String(form.get("repeat_password") ?? "")) {
      setMessage({ kind: "error", text: "The two new passwords are different." });
      return;
    }
    setPending(true);
    const result = await postJson("/api/auth/password", {
      current_password: String(form.get("current_password") ?? ""),
      new_password: newPassword,
    });
    setPending(false);
    if (result.ok) {
      formElement.reset();
      setMessage({
        kind: "ok",
        text: "Password changed. Other devices have been signed out.",
      });
    } else {
      setMessage({ kind: "error", text: result.message });
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex max-w-sm flex-col gap-4">
      <label className="flex flex-col gap-1 text-sm font-medium">
        Current password
        <input
          name="current_password"
          type="password"
          autoComplete="current-password"
          required
          className="input"
        />
      </label>
      <label className="flex flex-col gap-1 text-sm font-medium">
        New password (at least 12 characters)
        <input
          name="new_password"
          type="password"
          autoComplete="new-password"
          minLength={12}
          required
          className="input"
        />
      </label>
      <label className="flex flex-col gap-1 text-sm font-medium">
        Repeat new password
        <input
          name="repeat_password"
          type="password"
          autoComplete="new-password"
          minLength={12}
          required
          className="input"
        />
      </label>
      {message && (
        <p
          role={message.kind === "error" ? "alert" : "status"}
          className={`rounded-md px-3 py-2 text-sm ${
            message.kind === "error" ? "bg-danger-soft text-danger" : "bg-success-soft text-success"
          }`}
        >
          {message.text}
        </p>
      )}
      <button type="submit" className="btn-primary" disabled={pending}>
        {pending ? "Saving…" : "Change password"}
      </button>
    </form>
  );
}
