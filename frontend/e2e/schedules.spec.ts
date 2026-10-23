import { mkdirSync, utimesSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { GOOD } from "./data";
import { PASSWORD, signInOk, unique } from "./helpers";

// The shared folder mounted into the stack (INBOX_HOST_DIR, default ./local-data/inbox).
const INBOX = process.env.E2E_INBOX_DIR ?? path.resolve(__dirname, "../../local-data/inbox");

test.beforeAll(() => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD (and E2E_EMAIL) for the admin account.");
});

test("a file dropped in the shared folder is picked up and run by a schedule", async ({ page }) => {
  const tag = unique();
  const name = `e2e-${tag}-stock.csv`;
  mkdirSync(INBOX, { recursive: true });
  const file = path.join(INBOX, name);
  writeFileSync(file, GOOD);
  // Pretend the copy finished an hour ago, so it is taken at once.
  const past = new Date(Date.now() - 3600_000);
  utimesSync(file, past, past);

  await signInOk(page);
  await page.goto("/admin/data");
  await page.getByRole("button", { name: "Check the folder now" }).click();
  const card = page.getByRole("listitem").filter({ hasText: name }).first();
  await expect(async () => {
    await page.reload();
    await expect(card.getByText("Ready")).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 60_000 });
  await expect(card).toContainText("from the shared folder");

  // A schedule, switched off so that only "Run now" starts it in this test.
  await page.goto("/admin/schedules");
  await page.getByRole("link", { name: "New schedule" }).click();
  await page.getByRole("textbox", { name: /^Name/ }).fill(`Stock ${tag}`);
  await page.getByLabel("Analysis").selectOption({ label: "Demo: stock value by plant" });
  await page.getByLabel("File name pattern").fill(`e2e-${tag}-*.csv`);
  await expect(page.getByLabel("Period end: rule")).toHaveValue("previous_month_end");
  await page.getByLabel("Switched on").uncheck();
  await page.getByRole("button", { name: "Save schedule" }).click();
  await expect(page).toHaveURL(/\/admin\/schedules$/);

  const item = page
    .getByRole("listitem")
    .filter({ has: page.getByRole("heading", { name: `Stock ${tag}` }) });
  await expect(item).toContainText("Every day at 06:00");
  await expect(item).toContainText("Last day of the previous month");
  await item.getByRole("button", { name: "Run now" }).click();

  await expect(page).toHaveURL(/\/admin\/runs\/\d+$/);
  await expect(page.getByText("All checks passed.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(name).first()).toBeVisible();

  // Clean up the schedule.
  await page.goto("/admin/schedules");
  page.once("dialog", (dialog) => void dialog.accept());
  await item.getByRole("button", { name: "Delete" }).click();
  await expect(item).toHaveCount(0);
});

test("a schedule with a missing file says what is missing", async ({ page }) => {
  const tag = unique();
  await signInOk(page);
  await page.goto("/admin/schedules/new");
  await page.getByRole("textbox", { name: /^Name/ }).fill(`Missing ${tag}`);
  await page.getByLabel("Analysis").selectOption({ label: "Demo: stock value by plant" });
  await page.getByLabel("File name pattern").fill(`nothing-${tag}*.xlsx`);
  await page.getByLabel("Switched on").uncheck();
  await page.getByRole("button", { name: "Save schedule" }).click();
  const item = page
    .getByRole("listitem")
    .filter({ has: page.getByRole("heading", { name: `Missing ${tag}` }) });
  await item.getByRole("button", { name: "Run now" }).click();
  await expect(item.getByRole("alert")).toContainText(
    `No ready file named like 'nothing-${tag}*.xlsx'`,
  );
  page.once("dialog", (dialog) => void dialog.accept());
  await item.getByRole("button", { name: "Delete" }).click();
  await expect(item).toHaveCount(0);
});
