"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { postJson } from "@/lib/api-errors";

export function LogoutButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);

  async function onClick() {
    setPending(true);
    await postJson("/api/auth/logout");
    router.replace("/admin/login");
    router.refresh();
  }

  return (
    <button type="button" onClick={onClick} disabled={pending} className="btn-secondary">
      {pending ? "Signing out…" : "Sign out"}
    </button>
  );
}
