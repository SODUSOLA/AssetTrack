import { expect, test, type Locator, type Page } from "@playwright/test";
import { PEOPLE, signInAndWait } from "./helpers";

/**
 * The whole life of a repair, as the people who do it: a device is registered and handed to a
 * unit, the unit raises a complaint, engineering takes it, repairs the device in-house and returns
 * it, and the unit confirms. Each step signs in as the right person, and each depends on the last.
 */
test.describe.configure({ mode: "serial" });

const serial = `E2E-${Date.now()}`;
let deviceUrl = "";
let assetTag = "";
let complaintUrl = "";
let ticketNo = "";

async function logEvent(page: Page, type: string, fill: (dialog: Locator) => Promise<void>) {
  await page.getByRole("button", { name: "Log an event" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("What happened").selectOption({ label: type });
  await fill(dialog);
  await dialog.getByRole("button", { name: "Record event" }).click();
  await expect(page.getByText(`${type} recorded`)).toBeVisible();
}

test("1. an engineer registers a device and hands it to the Registration Office", async ({
  page,
}) => {
  await signInAndWait(page, PEOPLE.engineer);
  await page.goto("/app/devices");
  await page.getByRole("button", { name: "Register a device" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Type of device").fill("printer");
  await dialog.getByLabel("Serial number").fill(serial);
  await dialog.getByLabel(/^Make/).fill("Brother");
  await dialog.getByLabel(/^Model/).fill("HL-L2350");
  await dialog.getByRole("button", { name: "Register" }).click();

  await expect(page.getByRole("heading", { name: /^LAS-ENG-\d+$/ })).toBeVisible();
  assetTag = (await page.getByRole("heading", { name: /^LAS-ENG-\d+$/ }).textContent())!.trim();
  deviceUrl = new URL(page.url()).pathname;
  await expect(page.getByText("In stock", { exact: true })).toBeVisible();

  await logEvent(page, "Handed to unit", async (d) => {
    await d.getByLabel("Unit receiving the device").selectOption({ label: "Registration Office" });
    await d.getByLabel("Received by").fill("Adebayo Ogunleye");
  });
  await expect(page.getByText("With unit", { exact: true })).toBeVisible();
  await expect(page.getByText(/Waiting for Registration Office to answer/)).toBeVisible();
});

test("2. the unit's representative confirms they received it", async ({ page }) => {
  await signInAndWait(page, PEOPLE.rep);
  await page.goto("/app/acknowledgements");
  const row = page.getByRole("row", { name: new RegExp(assetTag) });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Confirm" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Yes, confirm" }).click();
  await expect(page.getByText("Confirmed", { exact: true })).toBeVisible();
  await expect(row).toHaveCount(0); // answered, so it is no longer waiting
});

test("3. the representative raises a complaint about it", async ({ page }) => {
  await signInAndWait(page, PEOPLE.rep);
  await page.goto(deviceUrl);
  await page.getByRole("button", { name: "Raise a complaint" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Title").fill("Prints blank pages");
  await dialog.getByLabel("What is wrong").fill("Every page comes out blank since this morning.");
  await dialog.getByLabel("How urgent").selectOption({ label: "High" });
  await dialog.getByRole("button", { name: "Raise complaint" }).click();

  await expect(page.getByRole("heading", { name: /^TKT-\d{4}-\d+$/ })).toBeVisible();
  ticketNo = (await page.getByRole("heading", { name: /^TKT-\d{4}-\d+$/ }).textContent())!.trim();
  complaintUrl = new URL(page.url()).pathname;
  await expect(page.getByText("Open", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Nobody yet")).toBeVisible();
});

test("4. an engineer takes the complaint and receives the device for repair", async ({ page }) => {
  await signInAndWait(page, PEOPLE.engineer);
  await page.goto(complaintUrl);
  await page.getByRole("button", { name: "Take it" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Take it" }).click();
  await expect(page.getByText("In progress", { exact: true }).first()).toBeVisible();

  await page.goto(deviceUrl);
  await logEvent(page, "Received for repair", async (d) => {
    const select = d.getByLabel("Complaint this repair is for");
    const option = select.locator("option", { hasText: ticketNo });
    await select.selectOption({ value: (await option.getAttribute("value"))! });
    await d.getByLabel("Handed in by").fill("Adebayo Ogunleye");
  });
});

test("5. the representative confirms the device was received", async ({ page }) => {
  await signInAndWait(page, PEOPLE.rep);
  await page.goto("/app/acknowledgements");
  const row = page.getByRole("row", { name: new RegExp(assetTag) });
  await row.getByRole("button", { name: "Confirm" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Yes, confirm" }).click();
  await expect(page.getByText("Confirmed", { exact: true })).toBeVisible();
  await expect(row).toHaveCount(0); // answered, so it is no longer waiting
});

test("6. the engineer cannot resolve the complaint while the device is still in the workshop", async ({
  page,
}) => {
  await signInAndWait(page, PEOPLE.engineer);
  await page.goto(complaintUrl);
  await page.getByRole("button", { name: "Mark resolved" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("What was done").fill("Trying to close early");
  await dialog.getByRole("button", { name: "Mark resolved" }).click();
  await expect(dialog.getByRole("alert")).toContainText("has not been returned yet");
});

test("7. the engineer diagnoses, repairs and returns the device", async ({ page }) => {
  await signInAndWait(page, PEOPLE.engineer);
  await page.goto(deviceUrl);
  await logEvent(page, "Diagnosed", async (d) => {
    await d.getByLabel("What is wrong").fill("Imaging drum worn out");
  });
  await logEvent(page, "Repair started", async () => {});
  await logEvent(page, "Repair completed", async (d) => {
    await d.getByLabel("What was done").fill("Replaced the imaging drum and tested.");
  });
  await logEvent(page, "Returned to unit", async (d) => {
    await d.getByLabel("Collected by").fill("Adebayo Ogunleye");
  });
  await expect(page.getByText(/Waiting for Registration Office to answer/)).toBeVisible();
});

test("8. while the returned device waits, the complaint says to answer on the device", async ({
  page,
}) => {
  await signInAndWait(page, PEOPLE.rep);
  await page.goto(complaintUrl);
  await expect(page.getByText("Resolved, waiting for the unit").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Answer on the device" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm it is fixed" })).toHaveCount(0);
});

test("9. the representative confirms the returned device, which closes the complaint", async ({
  page,
}) => {
  await signInAndWait(page, PEOPLE.rep);
  await page.goto("/app/acknowledgements");
  const row = page.getByRole("row", { name: new RegExp(assetTag) });
  await row.getByRole("button", { name: "Confirm" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Yes, confirm" }).click();
  await expect(page.getByText("Confirmed", { exact: true })).toBeVisible();
  await expect(row).toHaveCount(0); // answered, so it is no longer waiting

  await page.goto(complaintUrl);
  await expect(page.getByText("Closed", { exact: true }).first()).toBeVisible();
  // Everything that happened is on the record, in order, and cannot be edited.
  await expect(page.getByRole("list", { name: /Comments/ })).toContainText("Status");
  await expect(page.getByRole("button", { name: /edit|delete/i })).toHaveCount(0);
});

test("10. the finished repair appears in the turnaround report", async ({ page }) => {
  await signInAndWait(page, PEOPLE.head);
  await page.goto("/app/reports?report=turnaround");
  await expect(page.getByRole("article", { name: "Repair turnaround" })).toBeVisible();
  await expect(page.getByRole("row", { name: new RegExp(assetTag) })).toBeVisible();
});
