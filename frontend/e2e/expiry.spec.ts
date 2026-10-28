import { expect, type Page, test } from "@playwright/test";

import { uploadCsv } from "./data";
import { MAILPIT_URL, PASSWORD, signInOk, unique } from "./helpers";

test.beforeAll(() => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD (and E2E_EMAIL) for the admin account.");
});

// Fake ZSTOCKREPORT snapshots (invented plants, materials and costs); SAP dates, day first.
const csv = (rows: string[][]) => Buffer.from(rows.map((r) => r.join(",")).join("\n") + "\n");
const HEADER = [
  "Material",
  "NPC CODE",
  "Material Description",
  "Plant",
  "Batch",
  "Unrestricted",
  "Quality Inspection",
  "Blocked",
  "WBS Element",
  "Unit Cost",
  "Expiry Date",
];

interface MailSummary {
  ID: string;
  Subject: string;
  To: { Address: string }[];
  Cc: { Address: string }[];
  Bcc: { Address: string }[];
  Attachments: number;
}

async function chooseFile(page: Page, input: string, fileName: string) {
  const select = page.getByRole("group", { name: new RegExp(`^${input}`) }).getByLabel("File");
  const option = select.locator("option", { hasText: fileName }).first();
  await select.selectOption(await option.getAttribute("value"));
}

test("expiry monitoring, the pharmacist's justification and the monthly e-mail", async ({
  page,
  request,
}) => {
  const tag = unique();
  const material = `9${tag.slice(-6)}`;
  await signInOk(page);
  await uploadCsv(
    page,
    `zstock-open-${tag}.csv`,
    csv([
      HEADER,
      [
        material,
        "N1",
        "Drug one (fake)",
        "1000",
        "B1",
        "100",
        "0",
        "0",
        "RMS-PRG-FND-CP",
        "10",
        "15.05.2026",
      ],
      [
        `${material}1`,
        "N2",
        "Drug two (fake)",
        "1000",
        "B2",
        "50",
        "0",
        "0",
        "RMS-OWN-ESE-RM",
        "20",
        "10.06.2026",
      ],
    ]),
    "ZSTOCKREPORT stock on hand",
  );
  await uploadCsv(
    page,
    `zstock-close-${tag}.csv`,
    csv([
      HEADER,
      [
        `${material}1`,
        "N2",
        "Drug two (fake)",
        "1000",
        "B2",
        "0",
        "0",
        "20",
        "RMS-OWN-ESE-RM",
        "20",
        "10.06.2026",
      ],
    ]),
    "ZSTOCKREPORT stock on hand",
  );

  await page.goto("/admin/runs/new?analysis=expiry_monitoring");
  await page.getByLabel("Name of this run").fill(`Expiry ${tag}`);
  await page.getByLabel("Opening date").fill("2026-03-31");
  await page.getByLabel("Closing date").fill("2026-06-30");
  await chooseFile(page, "ZSTOCKREPORT of the opening month", `zstock-open-${tag}.csv`);
  await chooseFile(page, "ZSTOCKREPORT of the closing month", `zstock-close-${tag}.csv`);
  for (const optional of ["Goods movements", "Plant names"]) {
    await page
      .getByRole("group", { name: new RegExp(`^${optional}`) })
      .getByLabel("File")
      .selectOption("");
  }
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page).toHaveURL(/\/admin\/runs\/\d+$/);
  await expect(page.getByText("All checks passed.")).toBeVisible({ timeout: 30_000 });
  // Projected 1,000 + 1,000; 20 x 20 = 400 expired: 1,600 saved.
  await expect(page.getByRole("region", { name: "Key figures" })).toContainText("1,600");

  await page.goto("/admin/expiry");
  const card = page.getByRole("listitem").filter({ hasText: `Expiry ${tag}` });
  await card.getByRole("button", { name: "Prepare the follow-up" }).click();
  await expect(card).toContainText("0 of 1 justified");
  const link = (await card
    .getByRole("link", { name: "Open the pharmacist's page" })
    .getAttribute("href"))!;

  // The pharmacist, without an account: "Other" needs the reason in words.
  await page.context().clearCookies();
  await page.goto(new URL(link).pathname);
  await expect(
    page.getByRole("heading", { name: /Stock expiry position at 30 June 2026/ }),
  ).toBeVisible();
  await page.getByLabel("Your name").fill("Sales pharmacist");
  const form = page.getByRole("form", { name: /Justification for Drug two/ });
  await form.getByLabel("Root cause").selectOption("Other (give the reason)");
  await form.getByLabel("Reason (required)").fill("Hospital order cancelled after delivery");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(form.getByRole("status")).toContainText("Saved.");
  await expect(page.getByRole("heading", { name: /1 of 1 done/ })).toBeVisible();
  // Nothing left at closing expires within six months: no measure to record.
  await expect(page.getByText("Nothing expires within six months.")).toBeVisible();

  await signInOk(page);
  await page.goto("/admin/expiry");
  const done = page.getByRole("listitem").filter({ hasText: `Expiry ${tag}` });
  await expect(done).toContainText("1 of 1 justified");
  await done.getByRole("button", { name: "Send the e-mail now" }).click();
  await expect(done.getByRole("status")).toContainText("being sent");
  let mail: MailSummary | undefined;
  await expect
    .poll(
      async () => {
        const search = await request.get(
          `${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:"pharmacist@example.com"`)}`,
        );
        const found = ((await search.json()) as { messages: MailSummary[] }).messages;
        mail = found.find((m) => m.Subject.includes("expired RWF 400"));
        return Boolean(mail);
      },
      { timeout: 20_000 },
    )
    .toBe(true);
  expect(mail!.Cc.map((c) => c.Address).sort()).toEqual([
    "manager.one@example.com",
    "manager.two@example.com",
  ]);
  expect(mail!.Bcc.map((b) => b.Address)).toEqual(["manager@example.com"]);
  expect(mail!.Attachments).toBe(1);
});
