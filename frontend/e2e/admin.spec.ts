import { expect, test } from "@playwright/test";
import { PEOPLE, signIn, signInAndWait, signOut } from "./helpers";

test.describe.configure({ mode: "serial" });

const email = `e2e.${Date.now()}@demo.test`;
let password = "";

test("the head of engineering adds a person and is shown a password once", async ({ page }) => {
  await signInAndWait(page, PEOPLE.head);
  await page.goto("/app/people");
  await page.getByRole("button", { name: "Add a person" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Full name").fill("Ngozi Test");
  await dialog.getByLabel("Email address").fill(email);
  await dialog.getByLabel("Role").selectOption({ label: "Auditor" });
  await dialog.getByRole("button", { name: "Add person" }).click();

  const shown = page.getByTestId("one-time-password");
  await expect(shown).toBeVisible();
  password = (await shown.textContent())!.trim();
  expect(password.length).toBeGreaterThanOrEqual(10);
  await page.getByRole("button", { name: "I have passed it on" }).click();
  await expect(shown).toHaveCount(0);
  await expect(page.getByRole("row", { name: /Ngozi Test/ })).toBeVisible();
  // Once closed, the password is nowhere on the page.
  expect(await page.locator("body").innerText()).not.toContain(password);
});

test("the new person signs in with it, and can read but not change anything", async ({ page }) => {
  await signIn(page, { email, name: "Ngozi" }, password);
  await expect(page.getByRole("heading", { name: /Welcome, Ngozi/ })).toBeVisible();
  await page.goto("/app/devices");
  await expect(page.getByRole("button", { name: "Register a device" })).toHaveCount(0);
  await signOut(page);
});

test("deactivating the account ends access", async ({ page }) => {
  await signInAndWait(page, PEOPLE.head);
  await page.goto("/app/people");
  const row = page.getByRole("row", { name: /Ngozi Test/ });
  await row.getByRole("button", { name: "Deactivate" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("never deleted");
  await dialog.getByRole("button", { name: "Yes, deactivate" }).click();
  await expect(row.getByText("Deactivated")).toBeVisible();
  await signOut(page);

  await signIn(page, { email, name: "Ngozi" }, password);
  await expect(page.getByRole("alert")).toContainText("That email and password do not match.");
});

test("the head of engineering cannot deactivate or demote themselves", async ({ page }) => {
  await signInAndWait(page, PEOPLE.head);
  await page.goto("/app/people");
  const row = page.getByRole("row", { name: /Funmilayo Adeyemi/ });
  await expect(row.getByRole("button", { name: "Deactivate" })).toHaveCount(0);
  await row.getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("dialog").getByLabel("Role")).toBeDisabled();
});

test("units can be added", async ({ page }) => {
  const code = `E${Date.now().toString().slice(-6)}`;
  await signInAndWait(page, PEOPLE.head);
  await page.goto("/app/units");
  await page.getByRole("button", { name: "Add a unit" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill(`Test Unit ${code}`);
  await dialog.getByLabel("Code").fill(code);
  await dialog.getByRole("button", { name: "Add unit" }).click();
  await expect(page.getByRole("row", { name: new RegExp(code) })).toBeVisible();
});
