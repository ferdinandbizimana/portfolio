import { expect, type Page } from "@playwright/test";

// Fake demo data only (see backend datasets/definitions.py).
export function demoCsv(rows: string[]): Buffer {
  return Buffer.from(["Plant;Material;Material Description;Quantity;Value", ...rows].join("\n"));
}

export const GOOD = demoCsv([
  "P100;M-0001;Gloves;1200;360000",
  "P100;M-0002;Syringe 5 ml;5000;250000",
  "P200;M-0001;Gloves;300;90000",
]);

export async function uploadCsv(page: Page, name: string, content: Buffer) {
  await page.goto("/admin/data");
  await page
    .getByLabel("Choose files to upload")
    .setInputFiles({ name, mimeType: "text/csv", buffer: content });
  const card = page.getByRole("listitem").filter({ hasText: name }).first();
  await expect(card.getByText("Ready")).toBeVisible({ timeout: 20_000 });
  await expect(card.getByText("Demo: stock balance (fake data)")).toBeVisible();
}

export async function runDemo(page: Page, fileName: string, label: string) {
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
