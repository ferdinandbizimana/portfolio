import { expect, test } from "@playwright/test";

import { demoCsv, GOOD, runDemo, uploadCsv } from "./data";
import { PASSWORD, signInOk, unique } from "./helpers";

test.beforeAll(() => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD (and E2E_EMAIL) for the admin account.");
});

test("upload, run, review the dashboard and download the reports", async ({ page }) => {
  const name = `stock-${unique()}.csv`;
  await signInOk(page);
  await uploadCsv(page, name, GOOD);
  await runDemo(page, name, `June ${unique()}`);

  await expect(page.getByText("All checks passed.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Checks (3 of 3 passed)")).toBeVisible();
  const value = page
    .locator("section[aria-label='Key figures'] div")
    .filter({ hasText: "Stock value" });
  await expect(value).toContainText("700,000");

  // Filter the detail table by plant.
  await page.getByLabel("Plant", { exact: true }).selectOption("P200");
  const lines = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "All lines" }) });
  await expect(lines.getByRole("row")).toHaveCount(2); // header + one line
  await page.getByRole("button", { name: "Reset" }).click();
  await expect(lines.getByRole("row")).toHaveCount(4);

  for (const [title, type] of [
    ["Excel workbook", "spreadsheetml"],
    ["Word report", "wordprocessingml"],
    ["PowerPoint slides", "presentationml"],
  ] as const) {
    const href = await page.getByRole("link", { name: new RegExp(title) }).getAttribute("href");
    const response = await page.request.get(href!);
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toContain(type);
  }
});

test("a file with a wrong value is refused with the exact place", async ({ page }) => {
  const name = `bad-${unique()}.csv`;
  await signInOk(page);
  await uploadCsv(page, name, demoCsv(["P100;M-1;Gloves;10;ten thousand"]));
  await runDemo(page, name, "Bad file");

  await expect(
    page.getByText("Some input files are not right. Nothing was calculated."),
  ).toBeVisible({
    timeout: 30_000,
  });
  await expect(
    page.getByText(
      `${name}, sheet 'CSV', row 2, column 'Value': 'ten thousand' is not a valid number`,
    ),
  ).toBeVisible();
});

test("compare two periods", async ({ page }) => {
  const march = `march-${unique()}.csv`;
  const june = `june-${unique()}.csv`;
  await signInOk(page);
  await uploadCsv(page, march, demoCsv(["P100;M-0001;Gloves;100;100000"]));
  await uploadCsv(page, june, demoCsv(["P100;M-0001;Gloves;150;150000"]));
  const marchLabel = `March ${unique()}`;
  const juneLabel = `June ${unique()}`;
  await runDemo(page, march, marchLabel);
  await expect(page.getByText("All checks passed.")).toBeVisible({ timeout: 30_000 });
  await runDemo(page, june, juneLabel);
  await expect(page.getByText("All checks passed.")).toBeVisible({ timeout: 30_000 });

  await page.goto("/admin/runs");
  await page.getByRole("row").filter({ hasText: marchLabel }).getByRole("checkbox").check();
  await page.getByRole("row").filter({ hasText: juneLabel }).getByRole("checkbox").check();
  await page.getByRole("link", { name: "Compare the two runs" }).click();
  await expect(page).toHaveURL(/\/admin\/runs\/compare\?/);

  const row = page.getByRole("row", { name: /^Stock value / });
  await expect(row).toContainText("100,000");
  await expect(row).toContainText("150,000");
  await expect(row).toContainText("Increase 50.0%");
});
