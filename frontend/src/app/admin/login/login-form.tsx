"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { postJson } from "@/lib/api-errors";

export function LoginForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError(null);
    const result = await postJson("/api/auth/login", {
      email: String(form.get("email") ?? ""),
      password: String(form.get("password") ?? ""),
    });
    if (result.ok) {
      router.replace("/admin");
      router.refresh();
      return;
    }
    setPending(false);
    setError(result.message);
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      <label className="flex flex-col gap-1 text-sm font-medium">
        E-mail
        <input
          name="email"
          type="email"
          autoComplete="username"
          required
          className="input"
          autoFocus
        />
      </label>
      <label className="flex flex-col gap-1 text-sm font-medium">
        Password
        <input
          name="password"
          type="password"
          autoComplete="current-password"
          required
          className="input"
        />
      </label>
      {error && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}
      <button type="submit" className="btn-primary" disabled={pending}>
        {pending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
