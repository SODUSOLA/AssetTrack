import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { expect, type Page } from "@playwright/test";

export const PASSWORD = process.env.E2E_PASSWORD ?? "e2e-Password-123";

export const PEOPLE = {
  head: { email: "head@demo.test", name: "Funmilayo" },
  engineer: { email: "emeka@demo.test", name: "Emeka" },
  rep: { email: "adebayo@demo.test", name: "Adebayo" }, // Registration Office
  otherRep: { email: "chioma@demo.test", name: "Chioma" }, // Enrolment Centre
  auditor: { email: "auditor@demo.test", name: "Ngozi" },
} as const;

let counter = 0;

/**
 * Sign in through the real sign-in page. The API allows 5 sign-ins a minute per address, so each
 * sign-in comes from its own (forwarded) address; the e2e server trusts that header.
 */
export async function signIn(
  page: Page,
  who: { email: string; name: string },
  password = PASSWORD,
  path = "/app/",
) {
  counter += 1;
  const address = `10.${(Date.now() >> 8) & 255}.${Math.floor(counter / 250) % 250}.${(counter % 250) + 1}`;
  await page.context().setExtraHTTPHeaders({ "X-Forwarded-For": address });
  await page.goto(path);
  await page.getByLabel("Email address").fill(who.email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

export async function signInAndWait(page: Page, who: { email: string; name: string }) {
  await signIn(page, who);
  await expect(
    page.getByRole("heading", { name: new RegExp(`Welcome, ${who.name}`) }),
  ).toBeVisible();
}

export async function signOut(page: Page) {
  await page.getByRole("button", { name: /Account menu/ }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
}

const require = createRequire(import.meta.url);

/**
 * Run axe-core in the real browser, so colour contrast and layout-dependent rules are checked
 * with the real CSS (jsdom cannot do that).
 */
export async function expectNoAccessibilityViolations(page: Page, context = "page") {
  const source = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
  await page.evaluate(source);
  const violations = await page.evaluate(async () => {
    const axe = (
      window as unknown as {
        axe: {
          run: (
            c?: unknown,
            o?: unknown,
          ) => Promise<{
            violations: Array<{
              id: string;
              impact: string;
              nodes: Array<{ target: string[]; html: string }>;
            }>;
          }>;
        };
      }
    ).axe;
    const result = await axe.run(document, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
    });
    return result.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ")),
    }));
  });
  expect(violations, `accessibility violations on ${context}`).toEqual([]);
}

/** No sideways scrolling: the page is never wider than the screen. */
export async function expectNoHorizontalScroll(page: Page, context = "page") {
  const { scroll, inner } = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    inner: window.innerWidth,
  }));
  expect(scroll, `${context} scrolls sideways`).toBeLessThanOrEqual(inner);
}
