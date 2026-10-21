import { expect, test, type Page } from "@playwright/test";

import { GOOD, runDemo, uploadCsv } from "./data";
import { PASSWORD, signInOk, unique } from "./helpers";

test.beforeAll(() => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD (and E2E_EMAIL) for the admin account.");
});

async function publishRun(page: Page, title: string, detail: boolean) {
  const name = `pub-${unique()}.csv`;
  await uploadCsv(page, name, GOOD);
  await runDemo(page, name, `Run for ${title}`);
  await expect(page.getByText("All checks passed.")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("link", { name: "Publish…" }).click();
  await expect(page).toHaveURL(/\/publish$/);
  await page.getByLabel("Title").fill(title);
  if (detail) await page.getByLabel(/^Full detail/).check();
}

function item(page: Page, title: string) {
  return page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: title }) });
}

test("publish, share by secret link, make public and unpublish", async ({ page, browser }) => {
  const title = `Stock dashboard ${unique()}`;
  await signInOk(page);
  await publishRun(page, title, false);

  // The preview shows the summary only: the line-level table is left out.
  const preview = page.locator("section").filter({ hasText: "Preview: what visitors will see" });
  await expect(preview.getByRole("heading", { name: "By plant" })).toBeVisible();
  await expect(preview.getByRole("heading", { name: "All lines" })).toHaveCount(0);
  await expect(preview.getByText(/Checks \(/)).toHaveCount(0);

  await page.getByRole("button", { name: "Create (private)" }).click();
  await expect(page).toHaveURL(/\/admin\/publications$/);
  const entry = item(page, title);
  await expect(entry).toContainText("Summary only");

  // Visitors use a separate browser context with no admin session.
  const visitor = await browser.newPage();
  await visitor.goto("/dashboards");
  await expect(visitor.getByText(title)).toHaveCount(0);

  // Secret link: reachable with the link, not listed.
  await entry.getByLabel("Who can see it").selectOption("secret");
  const shared = entry.getByRole("link", { name: "Open shared link" });
  await expect(shared).toBeVisible();
  const sharedPath = (await shared.getAttribute("href"))!;
  await visitor.goto(sharedPath);
  await expect(visitor.getByRole("heading", { name: title, level: 1 })).toBeVisible();
  await expect(visitor.getByText("700,000").first()).toBeVisible();
  await expect(visitor.getByRole("heading", { name: "All lines" })).toHaveCount(0);
  await visitor.goto("/dashboards");
  await expect(visitor.getByText(title)).toHaveCount(0);

  // A new link replaces the old one.
  page.once("dialog", (dialog) => void dialog.accept());
  await entry.getByRole("button", { name: "New shared link" }).click();
  await expect(shared).not.toHaveAttribute("href", sharedPath);
  const oldLink = await visitor.goto(sharedPath);
  expect(oldLink?.status()).toBe(404);

  // Public: listed on the Dashboards page and in the site menu.
  await entry.getByLabel("Who can see it").selectOption("public");
  const publicLink = entry.getByRole("link", { name: "Open public page" });
  await expect(publicLink).toBeVisible();
  const publicPath = (await publicLink.getAttribute("href"))!;
  await visitor.goto("/");
  await visitor.getByRole("navigation").getByRole("link", { name: "Dashboards" }).click();
  await visitor.getByRole("link", { name: new RegExp(title) }).click();
  await expect(visitor).toHaveURL(new RegExp(`${publicPath}$`));
  await expect(visitor.getByRole("heading", { name: title, level: 1 })).toBeVisible();

  // Unpublish: every link stops working.
  page.once("dialog", (dialog) => void dialog.accept());
  await entry.getByRole("button", { name: "Unpublish" }).click();
  await expect(item(page, title)).toHaveCount(0);
  expect((await visitor.goto(publicPath))?.status()).toBe(404);
  await visitor.goto("/dashboards");
  await expect(visitor.getByText(title)).toHaveCount(0);
  await visitor.close();
});

test("a full-detail publication with checks shows the lines and checks", async ({
  page,
  browser,
}) => {
  const title = `Detail dashboard ${unique()}`;
  await signInOk(page);
  await publishRun(page, title, true);
  await page.getByLabel("Show the self-checks").check();
  const preview = page.locator("section").filter({ hasText: "Preview: what visitors will see" });
  await expect(preview.getByRole("heading", { name: "All lines" })).toBeVisible();
  await page.getByRole("button", { name: "Create (private)" }).click();

  const entry = item(page, title);
  await entry.getByLabel("Who can see it").selectOption("secret");
  const sharedPath = (await entry
    .getByRole("link", { name: "Open shared link" })
    .getAttribute("href"))!;
  const visitor = await browser.newPage();
  await visitor.goto(sharedPath);
  await expect(visitor.getByRole("heading", { name: "All lines" })).toBeVisible();
  await expect(visitor.getByText("Checks (3 of 3 passed)")).toBeVisible();
  await expect(visitor.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  await visitor.close();

  page.once("dialog", (dialog) => void dialog.accept());
  await entry.getByRole("button", { name: "Unpublish" }).click();
  await expect(item(page, title)).toHaveCount(0);
});
