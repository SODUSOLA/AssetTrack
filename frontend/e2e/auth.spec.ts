import { expect, test } from "@playwright/test";
import { PASSWORD, PEOPLE, signIn, signInAndWait, signOut } from "./helpers";

test.describe("signing in and out", () => {
  test("wrong password is refused without saying which part was wrong", async ({ page }) => {
    await signIn(page, PEOPLE.head, "not-the-password");
    await expect(page.getByRole("alert")).toContainText("That email and password do not match.");
    await expect(page.getByLabel("Password")).toHaveValue("");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });

  test("a good sign-in lands on the dashboard and survives a reload", async ({ page }) => {
    await signInAndWait(page, PEOPLE.head);
    await page.reload();
    await expect(page.getByRole("heading", { name: /Welcome, Funmilayo/ })).toBeVisible();
    // The token lives in memory only: nothing sensitive is left in browser storage.
    const stored = await page.evaluate(() =>
      JSON.stringify({ ...localStorage, ...sessionStorage }),
    );
    expect(stored).not.toMatch(/eyJ/); // a JWT always starts like this
    expect(stored).not.toContain(PASSWORD);
  });

  test("a signed-out visitor is sent to sign in, then back to where they were going", async ({
    page,
  }) => {
    await signIn(page, PEOPLE.engineer, PASSWORD, "/app/complaints");
    await expect(page.getByRole("heading", { name: "Complaints", exact: true })).toBeVisible();
    expect(new URL(page.url()).pathname).toBe("/app/complaints");
  });

  test("signing out ends the session: going back shows no data", async ({ page }) => {
    await signInAndWait(page, PEOPLE.head);
    await signOut(page);
    await page.goto("/app/devices");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });

  test("too many wrong attempts are slowed down", async ({ page }) => {
    await page.context().setExtraHTTPHeaders({ "X-Forwarded-For": "10.250.250.250" });
    await page.goto("/app/login");
    for (let attempt = 0; attempt < 6; attempt++) {
      await page.getByLabel("Email address").fill(PEOPLE.head.email);
      await page.getByLabel("Password").fill(`wrong-password-${attempt}`);
      await page.getByRole("button", { name: "Sign in" }).click();
      await expect(page.getByRole("alert")).toBeVisible();
    }
    await expect(page.getByRole("alert")).toContainText("Too many attempts");
  });
});
