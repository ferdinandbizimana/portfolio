import { expect, test, type Page } from "@playwright/test";

import { PASSWORD, signInOk, unique } from "./helpers";

test.beforeAll(() => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD (and E2E_EMAIL) for the admin account.");
});

// Fake demo data only (see backend datasets/definitions.py).
function demoCsv(rows: string[]): Buffer {
  return Buffer.from(["Plant;Material;Material Description;Quantity;Value", ...rows].join("\n"));
}

const GOOD = demoCsv([
  "P100;M-0001;Gloves;1200;360000",
  "P100;M-0002;Syringe 5 ml;5000;250000",
  "P200;M-0001;Gloves;300;90000",
]);

async function uploadCsv(page: Page, name: string, content: Buffer) {
  await page.goto("/admin/data");
  await page
    .getByLabel("Choose files to upload")
    .setInputFiles({ name, mimeType: "text/csv", buffer: content });
  const card = page.getByRole("listitem").filter({ hasText: name }).first();
  await expect(card.getByText("Ready")).toBeVisible({ timeout: 20_000 });
  await expect(card.getByText("Demo: stock balance (fake data)")).toBeVisible();
}

async function runDemo(page: Page, fileName: string, label: string) {
  await page.goto("/admin/analyses");
  await page.getByRole("link", { name: "Run", exact: true }).first().click();
  await page.getByLabel("Name of this run").fill(label);
  await page.getByLabel("Period end").fill("2026-06-30");
  const fileSelect = page.getByLabel("File");
  const option = fileSelect.locator("option", { hasText: fileName }).first();
  await fileSelect.selectOption(await option.getAttribute("value"));
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page).toHaveURL(/\/admin\/runs\/\d+$/);
}

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
