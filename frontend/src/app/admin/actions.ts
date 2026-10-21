"use server";

import { updateTag } from "next/cache";

import { PORTFOLIO_TAG } from "@/lib/portfolio";
import { getCurrentUser } from "@/lib/server-api";

/** Refresh the cached public pages after an edit. Only for the signed-in admin. */
export async function refreshPublicPages(): Promise<void> {
  if (!(await getCurrentUser())) return;
  updateTag(PORTFOLIO_TAG);
}
