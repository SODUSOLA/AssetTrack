import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/test/server";
import { authedFetch, api, unwrap } from "./client";
import { ApiError } from "./errors";
import { REFRESH_URL, session } from "./session";

const BASE = "http://localhost:3000/api/v1";
const refreshOk = (token: string) =>
  HttpResponse.json({ access_token: token, token_type: "bearer", expires_in: 1800 });
const get = (path = "/things") => authedFetch(new Request(`${BASE}${path}`));

describe("session", () => {
  it("keeps the token in memory only", () => {
    session.start("secret-token", 1800);
    expect(session.getToken()).toBe("secret-token");
    expect(JSON.stringify(localStorage)).not.toContain("secret-token");
    expect(JSON.stringify(sessionStorage)).not.toContain("secret-token");
  });

  it("shares one refresh between concurrent callers", async () => {
    let calls = 0;
    server.use(
      http.post(REFRESH_URL, async () => {
        calls += 1;
        await new Promise((resolve) => setTimeout(resolve, 20));
        return refreshOk("new");
      }),
    );
    const results = await Promise.all([session.refresh(), session.refresh(), session.refresh()]);
    expect(calls).toBe(1);
    expect(results.every((r) => r.ok && r.token === "new")).toBe(true);
  });

  it("reports a refused refresh as denied and an unreachable server as a network failure", async () => {
    server.use(http.post(REFRESH_URL, () => new HttpResponse(null, { status: 401 })));
    expect(await session.refresh()).toEqual({ ok: false, reason: "denied" });

    server.use(http.post(REFRESH_URL, () => HttpResponse.error()));
    expect(await session.refresh()).toEqual({ ok: false, reason: "network" });
  });

  it("refreshes ahead of expiry instead of sending a stale token", async () => {
    session.start("old", 5); // inside the early-refresh window
    server.use(http.post(REFRESH_URL, () => refreshOk("fresh")));
    expect(await session.tokenForRequest()).toBe("fresh");
  });

  it("tells listeners when the session expires", () => {
    const listener = vi.fn();
    const off = session.onExpired(listener);
    session.start("t", 1800);
    session.expire();
    expect(listener).toHaveBeenCalledTimes(1);
    expect(session.getToken()).toBeNull();
    off();
  });
});

describe("authedFetch", () => {
  it("sends the bearer token", async () => {
    session.start("abc", 1800);
    let auth: string | null = null;
    server.use(
      http.get(`${BASE}/things`, ({ request }) => {
        auth = request.headers.get("authorization");
        return HttpResponse.json({ ok: true });
      }),
    );
    await get();
    expect(auth).toBe("Bearer abc");
  });

  it("refreshes once on 401 and retries with the new token", async () => {
    session.start("expired", 1800);
    const seen: Array<string | null> = [];
    server.use(
      http.get(`${BASE}/things`, ({ request }) => {
        const auth = request.headers.get("authorization");
        seen.push(auth);
        return auth === "Bearer renewed"
          ? HttpResponse.json({ ok: true })
          : new HttpResponse(null, { status: 401 });
      }),
      http.post(REFRESH_URL, () => refreshOk("renewed")),
    );
    const response = await get();
    expect(response.status).toBe(200);
    expect(seen).toEqual(["Bearer expired", "Bearer renewed"]);
  });

  it("re-sends a request body on the retry", async () => {
    session.start("expired", 1800);
    const bodies: unknown[] = [];
    server.use(
      http.post(`${BASE}/things`, async ({ request }) => {
        bodies.push(await request.json());
        return request.headers.get("authorization") === "Bearer renewed"
          ? HttpResponse.json({ ok: true })
          : new HttpResponse(null, { status: 401 });
      }),
      http.post(REFRESH_URL, () => refreshOk("renewed")),
    );
    const response = await authedFetch(
      new Request(`${BASE}/things`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ a: 1 }),
      }),
    );
    expect(response.status).toBe(200);
    expect(bodies).toEqual([{ a: 1 }, { a: 1 }]);
  });

  it("ends the session when the refresh is refused", async () => {
    session.start("expired", 1800);
    const expired = vi.fn();
    session.onExpired(expired);
    server.use(
      http.get(`${BASE}/things`, () => new HttpResponse(null, { status: 401 })),
      http.post(REFRESH_URL, () => new HttpResponse(null, { status: 401 })),
    );
    const response = await get();
    expect(response.status).toBe(401);
    expect(expired).toHaveBeenCalledTimes(1);
    expect(session.getToken()).toBeNull();
  });

  it("keeps the session when the refresh failed only because the network did", async () => {
    session.start("expired", 1800);
    const expired = vi.fn();
    session.onExpired(expired);
    server.use(
      http.get(`${BASE}/things`, () => new HttpResponse(null, { status: 401 })),
      http.post(REFRESH_URL, () => HttpResponse.error()),
    );
    await get();
    expect(expired).not.toHaveBeenCalled();
  });

  it("does not try to refresh after a failed login", async () => {
    let refreshes = 0;
    server.use(
      http.post(`${BASE}/auth/login`, () => new HttpResponse(null, { status: 401 })),
      http.post(REFRESH_URL, () => {
        refreshes += 1;
        return refreshOk("x");
      }),
    );
    const response = await authedFetch(new Request(`${BASE}/auth/login`, { method: "POST" }));
    expect(response.status).toBe(401);
    expect(refreshes).toBe(0);
  });
});

describe("unwrap", () => {
  it("returns data", async () => {
    session.start("t", 1800);
    server.use(http.get(`${BASE}/auth/me`, () => HttpResponse.json({ id: "1", email: "a@b.c" })));
    const me = await unwrap(api.GET("/api/v1/auth/me"));
    expect(me).toMatchObject({ id: "1" });
  });

  it("turns the API error envelope into an ApiError with field errors", async () => {
    session.start("t", 1800);
    server.use(
      http.get(`${BASE}/auth/me`, () =>
        HttpResponse.json(
          {
            error: {
              code: "VALIDATION_ERROR",
              message: "Check the highlighted fields",
              details: { errors: [{ loc: ["body", "email"], msg: "Enter a valid email" }] },
            },
          },
          { status: 422 },
        ),
      ),
    );
    const failure = await unwrap(api.GET("/api/v1/auth/me")).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ status: 422, code: "VALIDATION_ERROR" });
    expect((failure as ApiError).fieldErrors).toEqual({ email: "Enter a valid email" });
  });

  it("reports an unreachable server as a network error", async () => {
    session.start("t", 1800);
    server.use(http.get(`${BASE}/auth/me`, () => HttpResponse.error()));
    const failure = await unwrap(api.GET("/api/v1/auth/me")).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).isNetwork).toBe(true);
  });
});
