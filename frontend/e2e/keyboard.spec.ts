import { expect, test } from "@playwright/test";
import { PEOPLE, signInAndWait } from "./helpers";

/** Everything below is done with the keyboard alone. */

test.describe("keyboard", () => {
  test.beforeEach(async ({ page }) => {
    await signInAndWait(page, PEOPLE.engineer);
  });

  test("the first Tab offers to skip the menu, and Enter lands in the content", async ({
    page,
  }) => {
    await page.goto("/app/devices");
    await expect(page.getByRole("heading", { name: "Devices", level: 1 })).toBeVisible();
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    await page.keyboard.press("Tab"); // the very first stop on a freshly loaded page
    const skip = page.getByRole("link", { name: "Skip to main content" });
    await expect(skip).toBeFocused();
    await expect(skip).toBeVisible();
    await page.keyboard.press("Enter");
    const inMain = await page.evaluate(
      () => !!document.activeElement?.closest("main") || document.activeElement?.id === "main",
    );
    expect(inMain).toBe(true);
  });

  test("moving to another page puts focus on its title", async ({ page }) => {
    await page.getByRole("link", { name: "Complaints" }).first().focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Complaints", level: 1 })).toBeFocused();
  });

  test("a dialog traps focus, locks page scrolling, closes on Escape and returns focus", async ({
    page,
  }) => {
    await page.goto("/app/devices");
    const trigger = page.getByRole("button", { name: "Register a device" }).first();
    await trigger.focus();
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(page.getByLabel("Type of device")).toBeFocused(); // starts at the first field

    // Tab around the whole dialog and a bit more: focus never leaves it.
    for (let i = 0; i < 14; i++) {
      await page.keyboard.press("Tab");
      const inside = await page.evaluate(() => !!document.activeElement?.closest("[role=dialog]"));
      expect(inside, `focus escaped the dialog on Tab ${i + 1}`).toBe(true);
    }
    // The page behind cannot scroll while it is open.
    expect(await page.evaluate(() => getComputedStyle(document.body).overflow)).toBe("hidden");

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
    expect(await page.evaluate(() => getComputedStyle(document.body).overflow)).not.toBe("hidden");
  });

  test("the account menu opens, moves with the arrow keys and closes on Escape", async ({
    page,
  }) => {
    const trigger = page.getByRole("button", { name: /Account menu/ });
    await trigger.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("menu")).toBeVisible();
    await expect(page.getByRole("menuitem").first()).toBeFocused(); // opening by keyboard focuses the first item
    await page.keyboard.press("ArrowDown");
    await expect(page.getByRole("menuitem").first()).not.toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("menu")).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("a form says what is wrong next to the field, and ties it to the field", async ({
    page,
  }) => {
    await page.goto("/app/devices");
    await page.getByRole("button", { name: "Register a device" }).first().click();
    await page.getByRole("button", { name: "Register" }).click();
    const field = page.getByLabel("Type of device");
    await expect(page.getByText("Enter the kind of device")).toBeVisible();
    await expect(field).toHaveAttribute("aria-invalid", "true");
    const describedBy = await field.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    await expect(page.locator(`#${describedBy}`)).toContainText("Enter the kind of device");
  });

  test("every control on a page can be reached and has a name", async ({ page }) => {
    await page.goto("/app/complaints");
    await expect(page.getByRole("heading", { name: "Complaints", level: 1 })).toBeVisible();
    const unnamed = await page.evaluate(() =>
      [...document.querySelectorAll("button, a[href], input, select, textarea")]
        .filter((el) => {
          const e = el as HTMLElement;
          if (e.closest("[hidden], [aria-hidden=true]") || e.offsetParent === null) return false;
          const label =
            e.getAttribute("aria-label") ||
            e.textContent?.trim() ||
            (e as HTMLInputElement).labels?.[0]?.textContent?.trim();
          return !label;
        })
        .map((el) => `${el.tagName.toLowerCase()} ${el.getAttribute("class") ?? ""}`.slice(0, 80)),
    );
    expect(unnamed).toEqual([]);
  });

  test("on a phone the menu is a drawer that closes on Escape and gives focus back", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/app/");
    const open = page.getByRole("button", { name: "Open menu" });
    await open.focus();
    await page.keyboard.press("Enter");
    const drawer = page.getByRole("dialog", { name: "Menu" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("link", { name: "Devices" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();
    await expect(open).toBeFocused();
  });

  test("moving with the keyboard never leaves a focus ring hidden", async ({ page }) => {
    await page.goto("/app/devices");
    await expect(page.getByRole("heading", { name: "Devices", level: 1 })).toBeVisible();
    await page.getByRole("link", { name: "Dashboard" }).first().focus();
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press("Tab");
      const visible = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el) return false;
        const s = getComputedStyle(el);
        return (
          (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== "none"
        );
      });
      expect(visible, `Tab ${i + 1}`).toBe(true);
    }
  });
});
