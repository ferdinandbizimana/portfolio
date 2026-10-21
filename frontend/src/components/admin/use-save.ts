"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { refreshPublicPages } from "@/app/admin/actions";
import { sendJson, type ApiResult } from "@/lib/api-errors";

type Message = { kind: "ok" | "error"; text: string } | null;

/** Send a change to the API, then refresh the public pages and this admin page. */
export function useSave() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<Message>(null);

  async function save<T>(
    method: "POST" | "PUT" | "DELETE",
    path: string,
    body?: unknown,
    okText = "Saved. The public site is updated.",
  ): Promise<ApiResult<T>> {
    setPending(true);
    setMessage(null);
    const result = await sendJson<T>(method, path, body);
    if (result.ok) {
      await refreshPublicPages();
      router.refresh();
      setMessage({ kind: "ok", text: okText });
    } else {
      setMessage({ kind: "error", text: result.message });
    }
    setPending(false);
    return result;
  }

  return { save, pending, message, setMessage };
}
