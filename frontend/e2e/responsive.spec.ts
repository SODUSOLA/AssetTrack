import { expect, test } from "@playwright/test";
import {
  expectNoAccessibilityViolations,
  expectNoHorizontalScroll,
  PEOPLE,
  signInAndWait,
} from "./helpers";

/**
 * Every page, at every screen size the project is tested at (see playwright.config.ts): nothing
 * scrolls sideways, and there are no accessibility violations in the light or dark theme.
 */
const PAGES: Array<{ path: string; heading: RegExp | string }> = [
  { path: "/app/", heading: /Welcome/ },
  { path: "/app/devices", heading: "Devices" },
  { path: "/app/complaints", heading: "Complaints" },
  { path: "/app/acknowledgements", heading: "Acknowledgements" },
  { path: "/app/reports?report=open-tickets", heading: "Reports" },
  { path: "/app/reports?report=turnaround", heading: "Reports" },
  { path: "/app/people", heading: "People" },
  { path: "/app/units", heading: "Units" },
  { path: "/app/account", heading: "Your account" },
];

for (const scheme of ["light", "dark"] as const) {
  test.describe(`${scheme} theme`, () => {
    test.beforeEach(async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      await signInAndWait(page, PEOPLE.head);
    });

    for (const { path, heading } of PAGES) {
      test(`${path} fits the screen and is accessible`, async ({ page }) => {
        await page.goto(path);
        await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
        // Wait for data to finish loading so the real content is what is checked.
        await expect(page.locator("[aria-busy='true']")).toHaveCount(0);
        await page.waitForLoadState("networkidle");
        await expectNoHorizontalScroll(page, path);
        await expectNoAccessibilityViolations(page, path);
      });
    }
  });
}

test("a device record and a complaint fit the screen and are accessible", async ({ page }) => {
  await signInAndWait(page, PEOPLE.head);
  await page.goto("/app/devices?q=LAS-ENG-000002");
  await page.getByRole("link", { name: "LAS-ENG-000002" }).first().click();
  await expect(page.getByRole("heading", { name: "LAS-ENG-000002", level: 1 })).toBeVisible();
  await page.waitForLoadState("networkidle");
  await expectNoHorizontalScroll(page, "device");
  await expectNoAccessibilityViolations(page, "device");

  await page.goto("/app/complaints");
  await page.getByRole("link", { name: /^TKT-/ }).first().click();
  await expect(page.getByRole("heading", { name: /^TKT-/, level: 1 })).toBeVisible();
  await page.waitForLoadState("networkidle");
  await expectNoHorizontalScroll(page, "complaint");
  await expectNoAccessibilityViolations(page, "complaint");
});

test("the sign-in page fits the screen and is accessible", async ({ page }) => {
  await page.goto("/app/login");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expectNoHorizontalScroll(page, "sign-in");
  await expectNoAccessibilityViolations(page, "sign-in");
});
