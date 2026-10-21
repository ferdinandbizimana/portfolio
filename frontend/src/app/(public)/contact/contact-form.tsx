"use client";

import { useState, type FormEvent } from "react";

import { postJson } from "@/lib/api-errors";

export function ContactForm() {
  const [state, setState] = useState<
    { kind: "idle" } | { kind: "sending" } | { kind: "sent" } | { kind: "error"; text: string }
  >({ kind: "idle" });

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setState({ kind: "sending" });
    const result = await postJson("/api/public/contact", {
      name: String(form.get("name") ?? ""),
      email: String(form.get("email") ?? ""),
      subject: String(form.get("subject") ?? ""),
      message: String(form.get("message") ?? ""),
      website: String(form.get("website") ?? ""),
    });
    if (result.ok) {
      formElement.reset();
      setState({ kind: "sent" });
    } else {
      setState({ kind: "error", text: result.message });
    }
  }

  if (state.kind === "sent") {
    return (
      <p role="status" className="rounded-md bg-success-soft px-4 py-3 text-success">
        Thank you. Your message has been sent, and I will reply by e-mail.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <label className="flex flex-col gap-1 text-sm font-medium">
        Your name
        <input name="name" required maxLength={120} autoComplete="name" className="input" />
      </label>
      <label className="flex flex-col gap-1 text-sm font-medium">
        Your e-mail
        <input
          name="email"
          type="email"
          required
          maxLength={320}
          autoComplete="email"
          className="input"
        />
      </label>
      <label className="flex flex-col gap-1 text-sm font-medium">
        Subject
        <input name="subject" required maxLength={200} className="input" />
      </label>
      <label className="flex flex-col gap-1 text-sm font-medium">
        Message
        <textarea
          name="message"
          required
          minLength={10}
          maxLength={5000}
          rows={6}
          className="input"
        />
      </label>
      {/* Hidden from people; spam robots fill it in. */}
      <div aria-hidden className="hidden">
        <label>
          Website
          <input name="website" tabIndex={-1} autoComplete="off" />
        </label>
      </div>
      {state.kind === "error" && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">
          {state.text}
        </p>
      )}
      <button type="submit" className="btn-primary self-start" disabled={state.kind === "sending"}>
        {state.kind === "sending" ? "Sending…" : "Send message"}
      </button>
    </form>
  );
}
