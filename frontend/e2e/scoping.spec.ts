import { expect, test } from "@playwright/test";
import { PEOPLE, signInAndWait } from "./helpers";

// The demo data: LAS-ENG-000002 is a printer in the Registration Office, with a disputed return.
test.describe("who can see what", () => {
  test("a unit representative cannot see another unit's device", async ({ page }) => {
    await signInAndWait(page, PEOPLE.otherRep);
    await page.goto("/app/devices?q=LAS-ENG-000002");
    await expect(page.getByText("No devices match")).toBeVisible();
    await expect(page.getByRole("link", { name: "LAS-ENG-000002" })).toHaveCount(0);
  });

  test("a representative only ever sees their own unit's complaints", async ({ page }) => {
    await signInAndWait(page, PEOPLE.rep);
    await page.goto("/app/complaints");
    await expect(page.getByRole("heading", { name: "Complaints", exact: true })).toBeVisible();
    await expect(page.getByLabel("Unit", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /TKT-/ }).first()).toBeVisible();
    await expect(page.locator("main")).not.toContainText("Enrolment Centre");
    await expect(page.locator("main")).not.toContainText("Finance and Accounts");
  });

  test("the admin pages are closed to everyone but the head of engineering", async ({ page }) => {
    await signInAndWait(page, PEOPLE.engineer);
    for (const path of ["/app/people", "/app/units"]) {
      await page.goto(path);
      await expect(page.getByText("Your role cannot open this page")).toBeVisible();
    }
    await expect(page.getByRole("link", { name: "People" })).toHaveCount(0);
  });

  test("an auditor can read but is offered no way to change anything", async ({ page }) => {
    await signInAndWait(page, PEOPLE.auditor);
    await page.goto("/app/devices");
    await expect(page.getByRole("heading", { name: "Devices", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Register a device" })).toHaveCount(0);
    await page.goto("/app/complaints");
    await expect(page.getByRole("button", { name: "Raise a complaint" })).toHaveCount(0);
  });

  test("the unit's own dispute is visible to engineering with the reason", async ({ page }) => {
    await signInAndWait(page, PEOPLE.engineer);
    await page.goto("/app/devices?q=LAS-ENG-000002");
    await page.getByRole("link", { name: "LAS-ENG-000002" }).first().click();
    await expect(page.getByText("Disputed")).toBeVisible();
    await expect(page.getByText("Prints, but pages come out streaked")).toBeVisible();
    // No vendor step is ever offered: repairs are in-house.
    await page.getByRole("button", { name: "Log an event" }).click();
    await expect(page.getByRole("dialog")).not.toContainText(/vendor/i);
  });

  test("the head of engineering sees what is overdue", async ({ page }) => {
    await signInAndWait(page, PEOPLE.head);
    await expect(page.getByText("Overdue answers")).toBeVisible();
    await expect(page.getByRole("link", { name: "Overdue answers" })).toBeVisible();
  });
});
