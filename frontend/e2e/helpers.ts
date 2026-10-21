import { expect, type Page } from "@playwright/test";

export const EMAIL = process.env.E2E_EMAIL ?? "admin@example.com";
export const PASSWORD = process.env.E2E_PASSWORD ?? "";
export const MAILPIT_URL = process.env.E2E_MAILPIT_URL ?? "http://localhost:8025";

export async function signIn(page: Page, password = PASSWORD) {
  await page.goto("/admin/login");
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

export async function signInOk(page: Page) {
  await signIn(page);
  await expect(page).toHaveURL(/\/admin$/);
}

/** A unique suffix so repeated runs do not collide. */
export function unique(): string {
  return `${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`;
}

// 1×1 PNG and a minimal PDF, enough for the upload type checks.
export const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);
export const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");
