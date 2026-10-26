import { expect, test } from "@playwright/test";

import { uploadCsv } from "./data";
import { MAILPIT_URL, PASSWORD, signInOk, unique } from "./helpers";

test.beforeAll(() => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD (and E2E_EMAIL) for the admin account.");
});

// Fake bin list and spot check (invented people, bins and products).
const csv = (rows: string[][]) => Buffer.from(rows.map((r) => r.join(",")).join("\n") + "\n");

interface MailSummary {
  ID: string;
  Subject: string;
  To: { Address: string }[];
  Bcc: { Address: string }[];
}

test("a spot check variance is assigned, e-mailed and corrected through its link", async ({
  page,
  request,
}) => {
  const tag = unique();
  const bin = `T${tag}`.toUpperCase();
  const email = `alice-${tag}@example.com`;
  await signInOk(page);
  await uploadCsv(
    page,
    `bins-${tag}.csv`,
    csv([
      ["RESPONSIBLE PERSON", "Storage Bin", "Storage Type", "Storage Section"],
      ["ALICE MUKAMANA", bin, "7000", "S1"],
      ["RECEIVING", `R${tag}`, "7050", ""],
      ["Name", "email", "", ""],
      ["Mukamana Alice", email, "", ""],
    ]),
    "Storage bins with responsible person",
  );
  await uploadCsv(
    page,
    `spot-${tag}.csv`,
    csv([
      [
        "Storage Bin",
        "Product",
        "Product Description",
        "Avail. Qty in AUoM",
        "Counted Quantities",
        "Variance",
      ],
      [bin, "1001", "Gloves", "10", "8", "-2"],
    ]),
    "Spot check sheet",
  );

  await page.goto("/admin/variances");
  const binList = page.getByLabel("Bin list");
  await binList.selectOption(
    await binList.locator("option", { hasText: `bins-${tag}.csv` }).getAttribute("value"),
  );
  await page.getByRole("button", { name: "Import bin list" }).click();
  await expect(page.getByRole("status")).toContainText("1 bins of warehouse units left out");

  const varianceFile = page.getByLabel("Variance file");
  await varianceFile.selectOption(
    await varianceFile.locator("option", { hasText: `spot-${tag}.csv` }).getAttribute("value"),
  );
  await page.getByRole("button", { name: "Create variances and send e-mails" }).click();
  await expect(page.getByRole("status")).toContainText("Spot check: 1 new variances");
  const row = page.getByRole("row").filter({ hasText: bin });
  await expect(row).toContainText("Open");
  await expect(row).toContainText("-2");

  // The worker e-mails the responsible person, with the manager in BCC.
  let mail: MailSummary | undefined;
  await expect
    .poll(
      async () => {
        const search = await request.get(
          `${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:"${email}"`)}`,
        );
        mail = ((await search.json()) as { messages: MailSummary[] }).messages[0];
        return mail?.Subject;
      },
      { timeout: 20_000 },
    )
    .toBe("Stock variances to correct: 1 new in your bins");
  expect(mail!.Bcc.map((b) => b.Address)).toEqual(["manager@example.com"]);
  const full = (await (await request.get(`${MAILPIT_URL}/api/v1/message/${mail!.ID}`)).json()) as {
    Text: string;
  };
  const link = full.Text.match(/https?:\/\/\S+\/variance\/\S+/)![0];

  // The person opens the link (no login needed) and records the correction.
  await page.context().clearCookies();
  await page.goto(new URL(link).pathname);
  await expect(page.getByRole("heading", { name: `Stock variance in bin ${bin}` })).toBeVisible();
  await page.getByLabel("Reason for the variance").fill("Picked from the wrong bin");
  await page.getByLabel("Responsible unit").selectOption("Picking");
  await page.getByLabel("Action taken").fill("Stock moved back to the bin");
  await page.getByRole("button", { name: "Mark as corrected" }).click();
  await expect(page.getByRole("status")).toContainText("recorded as corrected");

  await signInOk(page);
  await page.goto("/admin/variances");
  const done = page.getByRole("row").filter({ hasText: bin });
  await expect(done).toContainText("Corrected");
  await expect(done).toContainText("Picked from the wrong bin");
});

test("picker accuracy from the picking register", async ({ page }) => {
  const tag = unique();
  await signInOk(page);
  await uploadCsv(
    page,
    `pickers-${tag}.csv`,
    csv([
      [
        "Pickers name",
        "Numbers of lines picked per day",
        "Number of descrepancies out of those lines",
      ],
      ["ALICE", "40", "0"],
      ["Bob", "10", "2"],
    ]),
    "Picking register: lines and discrepancies per picker",
  );
  await page.goto("/admin/runs/new?analysis=picker_accuracy");
  await page.getByLabel("Name of this run").fill(`Pickers ${tag}`);
  const daily = page
    .getByRole("group", { name: /^Picking register: daily sheets/ })
    .getByLabel("File");
  await daily.selectOption(
    await daily.locator("option", { hasText: `pickers-${tag}.csv` }).getAttribute("value"),
  );
  await page
    .getByRole("group", { name: /^Picking register: sheets with one row/ })
    .getByLabel("File")
    .selectOption("");
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page).toHaveURL(/\/admin\/runs\/\d+$/);
  await expect(page.getByText("All checks passed.")).toBeVisible({ timeout: 30_000 });
  // 2 discrepancies in 50 lines: 96.0%; Bob (80%) is below the 98% target.
  const figures = page.getByRole("region", { name: "Key figures" });
  await expect(figures).toContainText("96.0%");
  await expect(
    page.getByRole("row").filter({ hasText: "Bob" }).filter({ hasText: "Below target" }),
  ).toBeVisible();
});
