import { expect, test, type Page } from "@playwright/test";

import { uploadCsv } from "./data";
import { PASSWORD, signInOk, unique } from "./helpers";

test.beforeAll(() => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD (and E2E_EMAIL) for the admin account.");
});

// Fake files with the real SAP column headers (invented plants, items and values).
const csv = (rows: string[][]) => Buffer.from(rows.map((r) => r.join(",")).join("\n") + "\n");
const PREVIOUS = csv([
  [
    "Valuation Area",
    "Material",
    "Material Description",
    "WBS",
    "Category",
    "Closing Stock",
    "Closing Value",
  ],
  ["1000", "101", "Net (fake)", "RMS-PRG-FND-CP", "MALARIA", "100", "10000"],
  ["1000", "102", "Kit (fake)", "RMS-PRG-FND-CP", "CPDS", "50", "5000"],
]);
const GL = csv([
  ["Plant", "Material", "WBS Element", "Quantity", "Amount in Local Currency"],
  ["1000", "101", "RMS-PRG-FND-CP", "120", "15000"],
  ["1000", "102", "RMS-PRG-FND-CP", "40", "4000"],
]);
const SCRAP = csv([
  ["Plant", "Material", "Movement Type", "WBS Element", "Quantity", "Amt.in Loc.Cur."],
  ["1000", "101", "551", "RMS-PRG-FND-CP", "-10", "-1000"],
  ["1000", "101", "101", "RMS-PRG-FND-CP", "30", "3000"],
]);

async function chooseFile(page: Page, input: string, fileName: string) {
  const box = page.locator("fieldset").filter({ hasText: input });
  const select = box.getByLabel("File");
  const option = select.locator("option", { hasText: fileName }).first();
  await select.selectOption(await option.getAttribute("value"));
}

test("RBC accountability report from uploaded SAP files", async ({ page }) => {
  const tag = unique();
  await signInOk(page);
  await uploadCsv(page, `previous-${tag}.csv`, PREVIOUS, "RBC report data (previous quarter)");
  await uploadCsv(page, `gl-${tag}.csv`, GL, "G/L line items (stock accounts)");
  await uploadCsv(page, `mb51-${tag}.csv`, SCRAP, "MB51 material documents");

  await page.goto("/admin/runs/new?analysis=rbc_accountability");
  await page.getByLabel("Name of this run").fill(`RBC ${tag}`);
  await page.getByLabel("Opening date").fill("2026-03-31");
  await page.getByLabel("Closing date").fill("2026-06-30");
  await expect(page.getByLabel("WBS element")).toHaveValue("RMS-PRG-FND-CP");
  await chooseFile(page, "Previous RBC report", `previous-${tag}.csv`);
  await chooseFile(page, "G/L line items", `gl-${tag}.csv`);
  await chooseFile(page, "MB51 material documents of the period", `mb51-${tag}.csv`);
  await page.getByRole("button", { name: "Run analysis" }).click();

  await expect(page).toHaveURL(/\/admin\/runs\/\d+$/);
  await expect(page.getByText("All checks passed.")).toBeVisible({ timeout: 30_000 });
  // 15,000 opening -> 14,000 + 4,000 = 18,000 closing: an increase of 20%.
  await expect(page.getByText("Overall stock position: Increase of 20.0%.")).toBeVisible();
  const programmes = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Summary by programme" }),
  });
  await expect(programmes.getByRole("row", { name: /MALARIA AND NTD/ })).toContainText("Increase");
  await expect(programmes.getByRole("row", { name: /^CPDS/ })).toContainText("Reduction");
  // MB51 receipts (101) on the WBS are shown next to opening and closing.
  await expect(programmes.getByRole("columnheader", { name: "Receipts (RWF)" })).toBeVisible();
  await expect(programmes.getByRole("row", { name: /MALARIA AND NTD/ })).toContainText("3,000");
  const workbook = await page.getByRole("link", { name: /Excel workbook/ }).getAttribute("href");
  expect((await page.request.get(workbook!)).status()).toBe(200);
});
