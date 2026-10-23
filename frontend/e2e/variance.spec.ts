import { expect, test } from "@playwright/test";

import { uploadCsv } from "./data";
import { PASSWORD, signInOk, unique } from "./helpers";

test.beforeAll(() => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD (and E2E_EMAIL) for the admin account.");
});

// Fake variance lines with the real column headers (invented plants and amounts).
const csv = (rows: string[][]) => Buffer.from(rows.map((r) => r.join(",")).join("\n") + "\n");
const LINES = csv([
  [
    "Plant",
    "Plant Description",
    "Material",
    "WBS Element",
    "Amount in Local Currency",
    "Final Validation Status",
    "ACTION",
    "REASON",
  ],
  [
    "1000",
    "Head office",
    "101",
    "RMS-PRG-FND-CP",
    "-100",
    "Justified",
    "DOCUMENTED",
    "Batch exchange",
  ],
  ["1000", "Head office", "102", "RMS-OWN-ESE-RM", "300", "JUSTIFIED", "DOCUMENTED", "Netting off"],
  ["7000", "Hub", "201", "RMS-OWN-ESE-RM", "50", "Not Justified - Pending", "RECOUNT", "Not found"],
]);

test("variance investigation from uploaded variance lines", async ({ page }) => {
  const tag = unique();
  await signInOk(page);
  await uploadCsv(
    page,
    `variance-${tag}.csv`,
    LINES,
    "Count variance lines (G/L, with investigation)",
  );

  await page.goto("/admin/runs/new?analysis=count_variance");
  await page.getByLabel("Name of this run").fill(`Count ${tag}`);
  await page.getByLabel("Count date").fill("2026-06-30");
  await expect(page.getByLabel("Tolerance")).toHaveValue("0.005");
  const box = page.locator("fieldset").filter({ hasText: "Variance lines" });
  const select = box.getByLabel("File");
  const option = select.locator("option", { hasText: `variance-${tag}.csv` }).first();
  await select.selectOption(await option.getAttribute("value"));
  await page.getByRole("button", { name: "Run analysis" }).click();

  await expect(page).toHaveURL(/\/admin\/runs\/\d+$/);
  await expect(page.getByText("All checks passed.")).toBeVisible({ timeout: 30_000 });
  const headline = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Headline results" }),
  });
  // positive 100; negative -300 - 50; absolute 450; Not Justified 50
  await expect(headline.getByRole("row", { name: /^Not Justified/ })).toContainText("50");
  await expect(page.getByText(/Inventory accuracy needs the final closing stock/)).toBeVisible();
  const plants = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Justification by plant" }),
  });
  await expect(plants.getByRole("row", { name: /Hub/ })).toContainText("0.0%");
});
