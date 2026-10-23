import { expect, type Page, test } from "@playwright/test";

import { uploadCsv } from "./data";
import { PASSWORD, signInOk, unique } from "./helpers";

test.beforeAll(() => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD (and E2E_EMAIL) for the admin account.");
});

// Fake data with the real column headers (invented materials, plants and amounts).
const csv = (rows: string[][]) => Buffer.from(rows.map((r) => r.join(",")).join("\n") + "\n");

const COUNTED = csv([
  [
    "ValA",
    "Material",
    "Sum of Closing Stock Posted In Finance",
    "Sum of Closing Value Posted In Finance",
    "Counted Quantities",
    "Counted Value",
    "Diff Between Counted Value and Closing Value",
    "Reasons for differences where Applicable",
  ],
  ["1000", "101", "10", "1000", "10", "1000", "0", "NO VARIANCE"],
  ["1000", "102", "10", "500", "12", "600", "100", "RECEIPT AFTER COUNTING"],
  ["7000", "103", "4", "400", "0", "0", "-400", "QC PLANT NOT COUNTED"],
]);

const WEEKLY = csv([
  ["Product code", "Product description", "RMS central warehouse", "RMS Branches", "SDPs", "AMC"],
  ["NPC1", "Drug A", "60", "0", "0", "10"],
  ["NPC2", "Drug B", "5", "0", "0", "10"],
  ["NPC3", "Drug C", "300", "0", "0", "10"],
]);

const STOCK = csv([
  [
    "Material",
    "NPC CODE",
    "Material Description",
    "Plant",
    "Unrestricted",
    "Quality Inspection",
    "Blocked",
    "WBS Element",
    "Unit Cost",
  ],
  ["1001", "NPC1", "Drug A", "1000", "10", "0", "0", "RMS-PRG-FND-CP", "2"],
  ["1003", "NPC3", "Drug C", "1000", "100", "0", "0", "RMS-PRG-FND-CP", "3"],
]);

async function chooseFile(page: Page, input: string, fileName: string) {
  const box = page.getByRole("group", { name: new RegExp(`^${input}`) });
  const select = box.getByLabel("File");
  const option = select.locator("option", { hasText: fileName }).first();
  await select.selectOption(await option.getAttribute("value"));
}

test("stock count reconciliation from closing vs counted stock", async ({ page }) => {
  const tag = unique();
  await signInOk(page);
  await uploadCsv(page, `counted-${tag}.csv`, COUNTED, "Closing vs counted stock (reconciliation)");

  await page.goto("/admin/runs/new?analysis=stock_count_reconciliation");
  await page.getByLabel("Name of this run").fill(`Reconciliation ${tag}`);
  await page.getByLabel("Count date").fill("2026-06-30");
  await chooseFile(page, "Closing vs counted stock", `counted-${tag}.csv`);
  await page.getByRole("button", { name: "Run analysis" }).click();

  await expect(page).toHaveURL(/\/admin\/runs\/\d+$/);
  await expect(page.getByText("All checks passed.")).toBeVisible({ timeout: 30_000 });
  // 100 - 400: net difference of -300 explained by the two reasons.
  for (const cause of [
    "Goods receipts posted after count",
    "Not counted – quality inspection (QI)",
  ]) {
    await expect(page.getByRole("cell", { name: cause, exact: true }).first()).toBeVisible();
  }
});

test("stock sufficiency against AMC uses every recognised sheet", async ({ page }) => {
  const tag = unique();
  await signInOk(page);
  await uploadCsv(page, `weekly-${tag}.csv`, WEEKLY, "Weekly stock monitoring (programme sheet)");
  await uploadCsv(page, `zstock-${tag}.csv`, STOCK, "ZSTOCKREPORT stock on hand");

  await page.goto("/admin/runs/new?analysis=stock_sufficiency_amc");
  await page.getByLabel("Name of this run").fill(`AMC ${tag}`);
  await page.getByLabel("Weekly report date").fill("2026-07-29");
  await chooseFile(page, "Weekly stock monitoring report", `weekly-${tag}.csv`);
  await expect(page.getByTestId("sheets-weekly")).toHaveText(
    "Every recognised sheet is used: CSV.",
  );
  await chooseFile(page, "ZSTOCKREPORT", `zstock-${tag}.csv`);
  const closing = page.getByRole("group", { name: /^Final closing stock/ });
  await closing.getByLabel("File").selectOption("");
  await page.getByRole("button", { name: "Run analysis" }).click();

  await expect(page).toHaveURL(/\/admin\/runs\/\d+$/);
  await expect(page.getByText("All checks passed.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/all recognised sheets/).first()).toBeVisible();
  const summary = page.locator("section").filter({
    has: page.getByRole("heading", { name: "AMC summary by programme" }),
  });
  // MOS 6 (to plan), 0.5 (stock-out risk) and 30 (overstock).
  await expect(summary.getByRole("row", { name: /^CSV/ })).toContainText("3");
  const risk = page.locator("section").filter({
    has: page.getByRole("heading", { name: /Products at risk/ }),
  });
  await expect(risk.getByRole("row", { name: /Drug B/ })).toBeVisible();
});
