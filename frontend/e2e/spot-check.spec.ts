import { expect, test } from "@playwright/test";

import { uploadCsv } from "./data";
import { PASSWORD, signInOk, unique } from "./helpers";

test.beforeAll(() => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD (and E2E_EMAIL) for the admin account.");
});

// Fake spot check with the headers of the weekly sheet (invented bins and products).
const csv = (rows: string[][]) => Buffer.from(rows.map((r) => r.join(",")).join("\n") + "\n");

test("spot check accuracy, raw and with explained variances left out", async ({ page }) => {
  const tag = unique();
  await signInOk(page);
  const file = `spotcheck-${tag}.csv`;
  await uploadCsv(
    page,
    file,
    csv([
      ["Storage Bin", "Product", "Qty AUoM", "ONHAND QTY", "VARIANCE", "Uunit cost", "COMMENT"],
      ["HQA01A", "P1", "100", "100", "0", "10", ""],
      ["HQA01B", "P2", "200", "150", "-50", "2", ""],
      ["HQA02A", "P3", "50", "60", "10", "5", "PICKED FOR OBD 1"],
      ["HQA02B", "P1", "100", "100", "0", "10", "BATCH: B5"],
    ]),
    "Spot check sheet",
  );
  await page.goto("/admin/runs/new?analysis=spot_check_accuracy");
  await page.getByLabel("Name of this run").fill(`Spot check ${tag}`);
  await page.getByLabel("Spot check date").fill("2026-09-17");
  const sheet = page
    .getByRole("group", { name: /^Spot check sheet \(this week\)/ })
    .getByLabel("File");
  await sheet.selectOption(
    await sheet.locator("option", { hasText: file }).first().getAttribute("value"),
  );
  for (const optional of [/^Previous spot check sheet/, /^Storage bins with responsible/]) {
    await page.getByRole("group", { name: optional }).getByLabel("File").selectOption("");
  }
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page).toHaveURL(/\/admin\/runs\/\d+$/);
  await expect(page.getByText("All checks passed.")).toBeVisible({ timeout: 30_000 });
  // 2 of 4 lines with a variance (line accuracy 50.0%); 1 explained by its comment (75.0%).
  const figures = page.getByRole("region", { name: "Key figures" });
  await expect(figures).toContainText("50.0%");
  await expect(figures).toContainText("75.0%");
  await expect(page.getByRole("link", { name: /Interactive dashboard/ }).first()).toBeVisible();
});
