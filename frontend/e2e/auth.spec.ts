import { expect, test } from "@playwright/test";

import { PASSWORD, signIn } from "./helpers";

test.beforeAll(() => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD (and E2E_EMAIL) for the admin account.");
});

test("the admin area sends visitors to the sign-in page", async ({ page }) => {
  await page.goto("/admin/activity");
  await expect(page).toHaveURL(/\/admin\/login$/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("a wrong password shows a clear message", async ({ page }) => {
  await signIn(page, "definitely not the password");
  await expect(page.locator("form").getByRole("alert")).toHaveText(
    "The e-mail or password is not correct.",
  );
  await expect(page).toHaveURL(/\/admin\/login$/);
});

test("sign in, see the activity log, sign out", async ({ page }) => {
  await signIn(page);
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();

  await page.getByRole("link", { name: "Activity log" }).first().click();
  await expect(page.getByRole("heading", { name: "Activity log" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Signed in" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "Failed sign-in" }).first()).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/admin\/login$/);
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/admin\/login$/);
});

test("change the password and change it back", async ({ page }) => {
  const temporary = `${PASSWORD}-temporary`;
  await signIn(page);
  await expect(page).toHaveURL(/\/admin$/);
  await page.goto("/admin/settings");

  async function change(from: string, to: string) {
    await page.getByLabel("Current password").fill(from);
    await page.getByLabel("New password (at least 12 characters)").fill(to);
    await page.getByLabel("Repeat new password").fill(to);
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(page.getByRole("status")).toContainText("Password changed");
  }

  await change(PASSWORD, temporary);
  await change(temporary, PASSWORD);
});
