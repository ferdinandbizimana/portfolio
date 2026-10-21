import { expect, test, type Page } from "@playwright/test";

import { GOOD, runDemo, uploadCsv } from "./data";
import { PASSWORD, signInOk, unique } from "./helpers";

/** Collects anything the browser blocked because of the Content Security Policy. */
function watchViolations(page: Page): string[] {
  const violations: string[] = [];
  page.on("console", (message) => {
    if (message.text().includes("Content Security Policy")) violations.push(message.text());
  });
  return violations;
}

test("security headers are sent", async ({ request }) => {
  const response = await request.get("/");
  const headers = response.headers();
  expect(headers["content-security-policy"]).toContain("default-src 'self'");
  expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["strict-transport-security"]).toContain("max-age=");
  expect(headers["server"]).toBeUndefined();
});

test("public pages work within the Content Security Policy", async ({ page }) => {
  const violations = watchViolations(page);
  for (const path of ["/", "/about", "/experience", "/skills", "/contact"]) {
    await page.goto(path);
    await expect(page.locator("main")).toBeVisible();
  }
  expect(violations).toEqual([]);
});

test("charts and admin pages work within the Content Security Policy", async ({ page }) => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD (and E2E_EMAIL) for the admin account.");
  const violations = watchViolations(page);
  await signInOk(page);
  const name = `csp-${unique()}.csv`;
  await uploadCsv(page, name, GOOD);
  await runDemo(page, name, `CSP ${unique()}`);
  await expect(page.getByText("All checks passed.")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("section svg").first()).toBeVisible();
  expect(violations).toEqual([]);
});

test("the overview shows that the worker and the scheduler are running", async ({ page }) => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD (and E2E_EMAIL) for the admin account.");
  await signInOk(page);
  const status = page.locator("section").filter({ hasText: "System status" });
  await expect(status.getByRole("listitem").filter({ hasText: "Worker" })).toContainText("OK");
  await expect(async () => {
    await page.reload();
    await expect(status.getByRole("listitem").filter({ hasText: "Scheduler" })).toContainText(
      "OK",
      { timeout: 1_000 },
    );
  }).toPass({ timeout: 90_000 });
  await expect(status.getByRole("listitem").filter({ hasText: "Disk space" })).toContainText(
    "GB free",
  );
});
