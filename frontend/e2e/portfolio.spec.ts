import { expect, test } from "@playwright/test";

import { MAILPIT_URL, PASSWORD, PDF, PNG, signInOk, unique } from "./helpers";

test.beforeAll(() => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD (and E2E_EMAIL) for the admin account.");
});

test("the public home page works without content and fits a phone screen", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});

test("profile edits, photo and CV appear on the public site at once", async ({ page }) => {
  const headline = `Supply chain analytics ${unique()}`;
  await signInOk(page);
  await page.goto("/admin/content/profile");
  await page.getByLabel("Headline").fill(headline);
  await page
    .getByLabel("Short introduction (home page)")
    .fill("I turn **SAP exports** into decisions.");
  await page
    .locator("input[type=file][accept^='image']")
    .setInputFiles({ name: "photo.png", mimeType: "image/png", buffer: PNG });
  await expect(page.getByRole("button", { name: "Replace…" }).first()).toBeVisible();
  await page
    .locator("input[type=file][accept='application/pdf']")
    .setInputFiles({ name: "CV Ferdinand.pdf", mimeType: "application/pdf", buffer: PDF });
  await expect(page.getByRole("link", { name: "CV Ferdinand.pdf" })).toBeVisible();
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByRole("status")).toContainText("Saved");

  await page.goto("/");
  await expect(page.getByText(headline)).toBeVisible();
  await expect(page.locator("strong", { hasText: "SAP exports" })).toBeVisible();
  const cvLink = page.getByRole("link", { name: "Download CV" }).first();
  const href = await cvLink.getAttribute("href");
  const download = await page.request.get(href!);
  expect(download.headers()["content-type"]).toBe("application/pdf");
});

test("experience and skills editors", async ({ page }) => {
  const role = `Stock analyst ${unique()}`;
  await signInOk(page);

  await page.goto("/admin/content/experience");
  await page.getByRole("button", { name: "Add a role" }).click();
  await page.getByLabel("Role", { exact: true }).fill(role);
  await page.getByLabel("Organisation").fill("Example Medical Supply");
  await page.getByLabel("Start month").fill("2022-04");
  await page.getByRole("button", { name: "Save role" }).click();
  await expect(page.getByText(`${role} · Example Medical Supply`)).toBeVisible();

  await page.goto("/experience");
  await expect(page.getByRole("heading", { name: role })).toBeVisible();
  await expect(page.getByText("Apr 2022 – Present").first()).toBeVisible();

  const group = `SAP ${unique()}`;
  await page.goto("/admin/content/skills");
  await page.getByRole("button", { name: "Add a skill group" }).click();
  await page.getByLabel("Group name").fill(group);
  await page.getByLabel("Skills").fill("MM\nEWM\nFI");
  await page.getByRole("button", { name: "Save group" }).click();
  await expect(page.getByText("MM, EWM, FI").first()).toBeVisible();

  await page.goto("/skills");
  await expect(page.getByRole("heading", { name: group })).toBeVisible();

  // Clean up so repeated runs stay tidy.
  page.on("dialog", (dialog) => void dialog.accept());
  await page.goto("/admin/content/experience");
  await page
    .getByRole("listitem")
    .filter({ hasText: role })
    .getByRole("button", { name: "Delete" })
    .click();
  await expect(page.getByText(role)).toHaveCount(0);
  await page.goto("/admin/content/skills");
  await page
    .getByRole("listitem")
    .filter({ hasText: group })
    .getByRole("button", { name: "Delete" })
    .click();
  await expect(page.getByText(group)).toHaveCount(0);
});

test("a project is visible only once published", async ({ page }) => {
  const title = `Stock count reconciliation ${unique()}`;
  await signInOk(page);
  await page.goto("/admin/content/projects/new");
  await page.getByLabel("Title").fill(title);
  const slug = await page.getByLabel("Address").inputValue();
  expect(slug).toMatch(/^stock-count-reconciliation-/);
  await page.getByLabel("Summary").fill("Count compared with system stock.");
  await page.getByLabel("Tags").fill("SAP MM, EWM");
  await page
    .getByLabel("Case study")
    .fill("## Approach\n\n| Step | Result |\n|---|---|\n| Count | Done |");
  await page.getByRole("button", { name: "Save project" }).click();
  await expect(page).toHaveURL(/\/admin\/content\/projects\/\d+$/);

  const draft = await page.request.get(`/projects/${slug}`);
  expect(draft.status()).toBe(404);

  await page.getByLabel("Published (visible on the public site)").check();
  await page.getByRole("button", { name: "Save project" }).click();
  await expect(page.getByRole("status")).toContainText("Saved");

  await page.goto("/projects");
  await page.getByRole("link", { name: new RegExp(title) }).click();
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Approach" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Done" })).toBeVisible();

  page.on("dialog", (dialog) => void dialog.accept());
  await page.goto("/admin/content/projects");
  await page
    .getByRole("listitem")
    .filter({ hasText: title })
    .getByRole("button", { name: "Delete" })
    .click();
  await expect(page.getByText(title)).toHaveCount(0);
  expect((await page.request.get(`/projects/${slug}`)).status()).toBe(404);
});

test("the contact form delivers an e-mail", async ({ page, request }) => {
  const subject = `Collaboration ${unique()}`;
  await page.goto("/contact");
  await page.getByLabel("Your name").fill("Amina Uwase");
  await page.getByLabel("Your e-mail").fill("amina@example.org");
  await page.getByLabel("Subject").fill(subject);
  await page.getByLabel("Message").fill("Hello, I would like to discuss a supply chain project.");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByRole("status")).toContainText("Your message has been sent");

  const search = await request.get(
    `${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`subject:"${subject}"`)}`,
  );
  const result = (await search.json()) as { messages: { Subject: string }[] };
  expect(result.messages.map((m) => m.Subject)).toEqual([`[Portfolio] ${subject}`]);
});
