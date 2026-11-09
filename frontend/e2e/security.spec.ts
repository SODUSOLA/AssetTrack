import { expect, test, type Page } from "@playwright/test";
import { PASSWORD, PEOPLE, signIn, signInAndWait, signOut } from "./helpers";

/** What a browser can be asked about the app's defences, checked on the real thing. */

const POLICY = "content security policy";

/** Collect every Content-Security-Policy violation the page reports while a test runs. */
function watchForCspViolations(page: Page) {
  const violations: string[] = [];
  page.on("console", (message) => {
    if (message.text().toLowerCase().includes(POLICY)) violations.push(message.text());
  });
  return violations;
}

test.describe("headers and cookies", () => {
  test("the app is served with a strict policy and clickjacking protection", async ({
    request,
  }) => {
    for (const path of ["/app/", "/app/devices", "/api/v1/health"]) {
      const response = await request.get(path);
      const headers = response.headers();
      expect(headers["x-content-type-options"], path).toBe("nosniff");
      expect(headers["x-frame-options"], path).toBe("DENY");
      expect(headers["referrer-policy"], path).toBeTruthy();
    }
    const policy = (await request.get("/app/")).headers()["content-security-policy"] ?? "";
    expect(policy).toContain("default-src 'self'");
    expect(policy).toContain("script-src 'self'");
    expect(policy).not.toContain("unsafe-inline");
    expect(policy).not.toContain("unsafe-eval");
    expect(policy).toContain("frame-ancestors 'none'");
    expect(policy).toContain("object-src 'none'");
  });

  test("the refresh token is an httpOnly, same-site cookie that only the auth endpoints receive", async ({
    page,
    context,
  }) => {
    await signInAndWait(page, PEOPLE.head);
    const cookie = (await context.cookies()).find((c) => c.name === "refresh_token");
    expect(cookie, "refresh cookie").toBeTruthy();
    expect(cookie!.httpOnly).toBe(true);
    expect(cookie!.sameSite).toBe("Strict");
    expect(cookie!.path).toBe("/api/v1/auth");
    // Script cannot read it.
    expect(await page.evaluate(() => document.cookie)).not.toContain("refresh_token");
  });

  test("signing out removes the cookie and revokes the session on the server", async ({
    page,
    context,
  }) => {
    await signInAndWait(page, PEOPLE.head);
    await signOut(page);
    expect((await context.cookies()).find((c) => c.name === "refresh_token")).toBeUndefined();
    const refresh = await page.request.post("/api/v1/auth/refresh");
    expect(refresh.status()).toBe(401);
  });
});

test.describe("nothing sensitive leaks", () => {
  test("no token or password is ever in storage, the address or a request address", async ({
    page,
  }) => {
    const addresses: string[] = [];
    page.on("request", (request) => addresses.push(request.url()));
    await signInAndWait(page, PEOPLE.head);
    for (const path of ["/app/devices", "/app/complaints", "/app/reports", "/app/people"]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
    }
    const stored = await page.evaluate(() =>
      JSON.stringify({ ...localStorage, ...sessionStorage }),
    );
    expect(stored).not.toMatch(/eyJ/);
    expect(stored).not.toContain(PASSWORD);
    expect(addresses.join("\n")).not.toMatch(/eyJ|password|token=|access_token/i);
    expect(page.url()).not.toMatch(/eyJ|password|token/i);
  });

  test("a server failure shows a plain message, not internals", async ({ page }) => {
    await signInAndWait(page, PEOPLE.head);
    await page.route("**/api/v1/devices?**", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: { code: "INTERNAL_ERROR", message: "An unexpected error occurred" },
        }),
      }),
    );
    await page.goto("/app/devices");
    await expect(page.getByRole("alert")).toContainText("could not be loaded");
    await expect(page.locator("body")).not.toContainText(/traceback|sqlalchemy|psycopg|stack/i);
  });
});

test.describe("hostile text is only ever text", () => {
  const hostile = `<img src=x onerror="window.__pwned=1"> <script>window.__pwned=1</script>`;

  test("a complaint titled with markup is shown as the literal text and nothing runs", async ({
    page,
  }) => {
    const violations = watchForCspViolations(page);
    await signInAndWait(page, PEOPLE.rep);
    await page.goto("/app/complaints");
    await page.getByRole("button", { name: "Raise a complaint" }).first().click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Title").fill(hostile);
    await dialog.getByLabel("What is wrong").fill(`${hostile}\n"quotes" & <b>bold</b>`);
    await dialog.getByRole("button", { name: "Raise complaint" }).click();

    await expect(page.getByRole("heading", { name: /^TKT-/ })).toBeVisible();
    await expect(page.getByText(hostile, { exact: false }).first()).toBeVisible(); // as text
    await expect(page.locator("main img[src='x']")).toHaveCount(0); // never became an element
    await page.goto("/app/complaints");
    await expect(page.getByText(hostile, { exact: false }).first()).toBeVisible();
    expect(
      await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned),
    ).toBeUndefined();
    expect(violations).toEqual([]);
  });

  test("hostile text in the address is not reflected as markup", async ({ page }) => {
    const violations = watchForCspViolations(page);
    await signInAndWait(page, PEOPLE.head);
    await page.goto(
      `/app/devices?q=${encodeURIComponent(hostile)}&status=${encodeURIComponent(hostile)}`,
    );
    await page.waitForLoadState("networkidle");
    await page.goto(
      `/app/reports?report=${encodeURIComponent(hostile)}&month=${encodeURIComponent(hostile)}`,
    );
    await page.waitForLoadState("networkidle");
    expect(
      await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned),
    ).toBeUndefined();
    await expect(page.locator("main img[src='x']")).toHaveCount(0);
    expect(violations).toEqual([]);
  });
});

test.describe("the page's own scripts and styles obey the policy", () => {
  test("browsing the main pages and opening dialogs causes no policy violations", async ({
    page,
  }) => {
    const violations = watchForCspViolations(page);
    await signInAndWait(page, PEOPLE.head);
    for (const path of [
      "/app/devices",
      "/app/complaints",
      "/app/acknowledgements",
      "/app/reports?report=turnaround",
      "/app/people",
      "/app/units",
      "/app/account",
    ]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
    }
    await page.goto("/app/devices");
    await page.getByRole("button", { name: "Register a device" }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: /Account menu/ }).click();
    await expect(page.getByRole("menu")).toBeVisible();
    expect(violations).toEqual([]);
  });

  test("the sign-in page applies the theme without an inline script", async ({ page }) => {
    const violations = watchForCspViolations(page);
    await page.emulateMedia({ colorScheme: "dark" });
    await page.goto("/app/login");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    expect(violations).toEqual([]);
    expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).not.toBe(
      "rgb(255, 255, 255)",
    );
  });

  test("a session cannot be reused after its refresh token is replayed", async ({
    page,
    context,
    request,
  }) => {
    // Replaying a rotated refresh token is treated as theft and ends every session.
    await signIn(page, PEOPLE.engineer);
    await expect(page.getByRole("heading", { name: /Welcome, Emeka/ })).toBeVisible();
    const stolen = (await context.cookies()).find((c) => c.name === "refresh_token")!;
    await page.reload(); // the app rotates the token once
    await expect(page.getByRole("heading", { name: /Welcome, Emeka/ })).toBeVisible();

    const replay = await request.post("/api/v1/auth/refresh", {
      headers: { cookie: `refresh_token=${stolen.value}`, "x-forwarded-for": "10.99.0.1" },
    });
    expect(replay.status()).toBe(401);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible(); // everyone is signed out
  });
});
