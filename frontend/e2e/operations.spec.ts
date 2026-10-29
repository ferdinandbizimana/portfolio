import { expect, type Page, test } from "@playwright/test";

import { uploadCsv } from "./data";
import { PASSWORD, signInOk, unique } from "./helpers";

test.beforeAll(() => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD (and E2E_EMAIL) for the admin account.");
});

// Fake exports with the real SAP column headers (invented documents, plants and quantities).
// Dates are written day first, as SAP list exports do.
const csv = (rows: string[][]) => Buffer.from(rows.map((r) => r.join(",")).join("\n") + "\n");

async function chooseFile(page: Page, input: string, fileName: string) {
  const box = page.getByRole("group", { name: new RegExp(`^${input}`) });
  const select = box.getByLabel("File");
  const option = select.locator("option", { hasText: fileName }).first();
  await select.selectOption(await option.getAttribute("value"));
}

async function clearFile(page: Page, input: string) {
  await page
    .getByRole("group", { name: new RegExp(`^${input}`) })
    .getByLabel("File")
    .selectOption("");
}

function kpi(page: Page, label: string) {
  return page
    .getByRole("region", { name: "Key figures" })
    .locator("div")
    .filter({ has: page.getByText(label, { exact: true }) });
}

async function run(page: Page, analysis: string, label: string, fill: () => Promise<void>) {
  await page.goto(`/admin/runs/new?analysis=${analysis}`);
  await page.getByLabel("Name of this run").fill(label);
  await fill();
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page).toHaveURL(/\/admin\/runs\/\d+$/);
  await expect(page.getByText("All checks passed.")).toBeVisible({ timeout: 30_000 });
}

test("order fill rate from VA05 and outbound deliveries", async ({ page }) => {
  const tag = unique();
  await signInOk(page);
  const orders = csv([
    [
      "Sales Document",
      "Sales Document Item",
      "Document Date",
      "Sold-to Party",
      "Material",
      "Order Quantity (Item)",
      "Net Value (Item)",
    ],
    [`9${tag.slice(-6)}1`, "10", "01.04.2026", "C1", "1001", "10", "1000"],
    [`9${tag.slice(-6)}1`, "20", "01.04.2026", "C1", "1002", "5", "500"],
  ]);
  const deliveries = csv([
    [
      "Delivery",
      "Reference Document",
      "Reference Item",
      "Material",
      "Plant",
      "Delivery Quantity",
      "Actual delivery qty",
      "Goods Issue Date",
      "Act. Gds Mvmnt Date",
    ],
    ["D1", `9${tag.slice(-6)}1`, "10", "1001", "1000", "10", "10", "05.04.2026", "05.04.2026"],
    ["D2", `9${tag.slice(-6)}1`, "20", "1002", "1000", "3", "3", "06.04.2026", "06.04.2026"],
  ]);
  // A second month of VA05: one more order, not delivered.
  const may = csv([
    [
      "Sales Document",
      "Sales Document Item",
      "Document Date",
      "Sold-to Party",
      "Material",
      "Order Quantity (Item)",
      "Net Value (Item)",
    ],
    [`9${tag.slice(-6)}2`, "10", "05.05.2026", "C1", "1001", "10", "1000"],
  ]);
  await uploadCsv(page, `va05-${tag}.csv`, orders, "VA05 sales orders");
  await uploadCsv(page, `va05-may-${tag}.csv`, may, "VA05 sales orders");
  await uploadCsv(page, `obd-${tag}.csv`, deliveries, "Outbound deliveries");
  await run(page, "order_fill_rate", `Fill rate ${tag}`, async () => {
    await page.getByLabel("Orders from").fill("2026-04-01");
    await page.getByLabel("Orders up to").fill("2026-06-30");
    await chooseFile(page, "Sales orders", `va05-${tag}.csv`);
    await page
      .getByRole("group", { name: /^More files for Sales orders/ })
      .getByLabel(`va05-may-${tag}.csv`)
      .check();
    await chooseFile(page, "Outbound deliveries", `obd-${tag}.csv`);
    await clearFile(page, "Plant and customer names");
    await clearFile(page, "Goods movements");
  });
  // April and May together: one of three lines in full; 13 of 25 units.
  await expect(kpi(page, "Line fill rate")).toContainText("33.3%");
  await expect(kpi(page, "Quantity fill rate")).toContainText("52.0%");
  await expect(page.getByText(`va05-may-${tag}.csv, sheet`)).toBeVisible();
  // The interactive dashboard opens sandboxed (own origin, no access to the site).
  const open = page.getByRole("link", { name: "Open interactive dashboard" });
  const view = await page.request.get((await open.getAttribute("href"))!);
  expect(view.status()).toBe(200);
  expect(view.headers()["content-security-policy"]).toContain("sandbox allow-scripts");
  expect(await view.text()).toContain("<title>Order fill rate</title>");
});

test("stock in transit traced through MB51", async ({ page }) => {
  const tag = unique();
  await signInOk(page);
  const sto = `45${tag.slice(-8)}`;
  const mb5t = csv([
    ["Supplying Plant", "Purchasing Document", "Plant", "Material", "Quantity", "Amt.in Loc.Cur."],
    ["1000", sto, "7000", "1001", "6", "600"],
  ]);
  const mb51 = csv([
    [
      "Plant",
      "Material",
      "Movement Type",
      "Quantity",
      "Amt.in Loc.Cur.",
      "WBS Element",
      "Posting Date",
      "Purchase order",
      "Reference",
    ],
    ["1000", "1001", "641", "-10", "-1000", "W", "01.07.2026", sto, "80001"],
    ["7000", "1001", "101", "4", "400", "W", "11.07.2026", sto, "80001"],
  ]);
  await uploadCsv(page, `mb5t-${tag}.csv`, mb5t, "MB5T stock in transit");
  await uploadCsv(page, `mb51-${tag}.csv`, mb51, "MB51 material documents");
  await run(page, "stock_in_transit", `Transit ${tag}`, async () => {
    await page.getByLabel("MB5T report date").fill("2026-07-31");
    await chooseFile(page, "Stock in transit", `mb5t-${tag}.csv`);
    await chooseFile(page, "Goods movements", `mb51-${tag}.csv`);
    await clearFile(page, "STO creation dates");
    await clearFile(page, "Plant names");
  });
  await expect(kpi(page, "Average transit time (received)")).toContainText("10");
  await expect(kpi(page, "Average days in transit (open)")).toContainText("30");
});

test("purchase order follow-up from ME2N and inbound deliveries", async ({ page }) => {
  const tag = unique();
  await signInOk(page);
  const po = `41${tag.slice(-8)}`;
  const me2n = csv([
    [
      "Purchasing Document",
      "Item",
      "Document Date",
      "Material",
      "Plant",
      "Order Quantity",
      "Still to be delivered (qty)",
      "Net Order Value",
    ],
    [po, "10", "10.01.2026", "1001", "1000", "100", "0", "10000"],
  ]);
  const inbound = csv([
    [
      "Delivery",
      "Purchasing Document",
      "Material",
      "Delivery Quantity",
      "Vendor",
      "Goods receipt date",
      "Act. Gds Mvmnt Date",
    ],
    ["IB1", po, "1001", "100", "V1", "11.03.2026", "11.03.2026"],
  ]);
  await uploadCsv(page, `me2n-${tag}.csv`, me2n, "ME2N / ME2M purchase orders");
  await uploadCsv(page, `inbound-${tag}.csv`, inbound, "Inbound deliveries");
  await run(page, "po_follow_up", `PO ${tag}`, async () => {
    await page.getByLabel("POs created from").fill("2025-07-01");
    await page.getByLabel("POs created up to").fill("2026-06-30");
    await page.getByLabel("Report date").fill("2026-07-31");
    await chooseFile(page, "Purchase orders", `me2n-${tag}.csv`);
    await chooseFile(page, "Inbound deliveries", `inbound-${tag}.csv`);
    await clearFile(page, "Plant names");
  });
  await expect(kpi(page, "Lines delivered in full")).toContainText("100.0%");
  await expect(kpi(page, "Average delivery period")).toContainText("60");
});

test("warehouse activity from EWM tasks", async ({ page }) => {
  const tag = unique();
  await signInOk(page);
  const tasks = csv([
    [
      "Warehouse Task",
      "Whse Process Category Desc.",
      "Source Storage Bin",
      "Destination Bin",
      "Product",
      "Warehouse Task Status",
      "Goods Receipt Date",
      "Confirmation Date",
      "Confirmation Time",
    ],
    [`W${tag}1`, "Putaway", "GR-ZONE", "A-01", "1001", "C", "01.07.2026", "03.07.2026", "09:00:00"],
  ]);
  await uploadCsv(page, `tasks-${tag}.csv`, tasks, "EWM warehouse tasks");
  await run(page, "warehouse_activity", `Warehouse ${tag}`, async () => {
    await page.getByLabel("Report date").fill("2026-07-31");
    await chooseFile(page, "Warehouse tasks", `tasks-${tag}.csv`);
    await clearFile(page, "Outbound deliveries");
    await clearFile(page, "Goods movements");
  });
  await expect(kpi(page, "Average dock to stock")).toContainText("2");
});

test("expiry risk at the AMC", async ({ page }) => {
  const tag = unique();
  await signInOk(page);

  const stock = csv([
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
      "Batch",
      "Expiry Date",
    ],
    [
      "1001",
      `N${tag}`,
      "Drug A",
      "1000",
      "10",
      "0",
      "0",
      "RMS-PRG-FND-CP",
      "2",
      "B1",
      "01.07.2026",
    ],
  ]);
  const weekly = csv([
    ["Product code", "Product description", "RMS central warehouse", "RMS Branches", "SDPs", "AMC"],
    [`N${tag}`, "Drug A", "10", "0", "0", "5"],
  ]);
  await uploadCsv(page, `zstock-${tag}.csv`, stock, "ZSTOCKREPORT stock on hand");
  await uploadCsv(page, `weekly-${tag}.csv`, weekly, "Weekly stock monitoring (programme sheet)");
  await run(page, "expiry_risk", `Expiry ${tag}`, async () => {
    await page.getByLabel("Stock report date").fill("2026-07-31");
    await chooseFile(page, "ZSTOCKREPORT", `zstock-${tag}.csv`);
    await chooseFile(page, "Weekly stock monitoring report", `weekly-${tag}.csv`);
    await clearFile(page, "Material master");
    await clearFile(page, "Plant names");
  });
  // The batch expired on 1 July: all of it (10 x 2) is at risk.
  await expect(kpi(page, "Expired stock")).toContainText("20");
  await expect(kpi(page, "Share of stock at risk")).toContainText("100.0%");
});
