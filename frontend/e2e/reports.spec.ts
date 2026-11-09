import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { PEOPLE, signInAndWait } from "./helpers";

test.describe("reports", () => {
  test.beforeEach(async ({ page }) => {
    await signInAndWait(page, PEOPLE.head);
    await page.goto("/app/reports?report=turnaround");
    await expect(page.getByRole("article", { name: "Repair turnaround" })).toBeVisible();
  });

  test("shows figures and tables, and leaves vendors off the screen", async ({ page }) => {
    await expect(page.getByLabel("Summary")).toContainText("Repairs returned");
    await expect(page.getByRole("table").first()).toBeVisible();
    await expect(page.locator("main")).not.toContainText(/vendor/i);
  });

  test("downloads an Excel workbook through the signed-in session", async ({ page }) => {
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Excel" }).click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/\.xlsx$/);
    const bytes = readFileSync((await file.path())!);
    expect(bytes.subarray(0, 2).toString()).toBe("PK"); // an .xlsx is a zip archive
  });

  test("downloads a PDF", async ({ page }) => {
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "PDF" }).click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/\.pdf$/);
    expect(
      readFileSync((await file.path())!)
        .subarray(0, 4)
        .toString(),
    ).toBe("%PDF");
  });

  test("prints as a clean page: no menu, no buttons, tables intact, light even in dark mode", async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await page.reload();
    await expect(page.getByRole("article", { name: "Repair turnaround" })).toBeVisible();

    await page.emulateMedia({ media: "print", colorScheme: "dark" });
    await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();
    await expect(page.getByRole("button", { name: "Print" })).toBeHidden();
    await expect(page.getByRole("button", { name: "Excel" })).toBeHidden();
    await expect(page.getByRole("table").first()).toBeVisible();
    await expect(
      page.getByText(/Printed from the LASRRA Engineering Audit Register/),
    ).toBeVisible();
    // The report fills the page: the hidden sidebar must not leave its column behind.
    const { main, width } = await page.evaluate(() => ({
      main: document.querySelector("main")!.getBoundingClientRect().width,
      width: window.innerWidth,
    }));
    expect(main).toBeGreaterThan(width * 0.85);
  });

  test("the Print button opens the print dialog", async ({ page }) => {
    await page.evaluate(() => {
      (window as unknown as { printed: number }).printed = 0;
      window.print = () => {
        (window as unknown as { printed: number }).printed += 1;
      };
    });
    await page.getByRole("button", { name: "Print" }).click();
    expect(await page.evaluate(() => (window as unknown as { printed: number }).printed)).toBe(1);
  });

  test("a bad period is explained, not shown as a failure", async ({ page }) => {
    await page.goto("/app/reports?report=turnaround&from=2026-10-31&to=2026-08-01");
    await expect(page.getByText("The start date must not be after the end date.")).toBeVisible();
  });
});
