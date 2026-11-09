/**
 * The signed-in session, held in memory only.
 *
 * The access token (30 minutes) lives in a module variable: never in localStorage, never in a
 * URL. The long-lived refresh token is an httpOnly cookie the browser handles; this code never
 * sees it. A reload therefore starts with a silent refresh.
 *
 * The server rotates the refresh token on every refresh and treats a reused one as theft,
 * ending every session. So two refreshes must never present the same cookie:
 *   - within a tab, concurrent callers share one in-flight refresh;
 *   - across tabs, a Web Lock serialises them, and the new access token is broadcast so a
 *     waiting tab can use it instead of refreshing again (BroadcastChannel is same-origin and
 *     memory-only).
 */

const BASE = import.meta.env.VITE_API_BASE ?? "";
export const REFRESH_URL = `${BASE}/api/v1/auth/refresh`;

const LOCK_NAME = "lasrra-refresh";
const CHANNEL_NAME = "lasrra-session";
/** Refresh a little early so a request does not race the expiry. */
const EARLY_REFRESH_MS = 20_000;

export type RefreshResult =
  { ok: true; token: string } | { ok: false; reason: "denied" | "network" };

type Message = { type: "token"; token: string; expiresAt: number } | { type: "logout" };

let token: string | null = null;
let expiresAt = 0;
let version = 0; // bumped whenever the token changes, here or in another tab
let inflight: Promise<RefreshResult> | null = null;
let channel: BroadcastChannel | null = null;

const expiredListeners = new Set<() => void>();

function getChannel(): BroadcastChannel | null {
  if (channel || typeof BroadcastChannel === "undefined") return channel;
  channel = new BroadcastChannel(CHANNEL_NAME);
  channel.onmessage = (event: MessageEvent<Message>) => {
    const message = event.data;
    if (message.type === "token") {
      token = message.token;
      expiresAt = message.expiresAt;
      version += 1;
    } else if (message.type === "logout") {
      token = null;
      expiresAt = 0;
      version += 1;
      expiredListeners.forEach((listener) => listener());
    }
  };
  return channel;
}

function withLock<T>(work: () => Promise<T>): Promise<T> {
  const locks = typeof navigator === "undefined" ? undefined : navigator.locks;
  return locks ? (locks.request(LOCK_NAME, work) as Promise<T>) : work();
}

function setToken(next: string, expiresInSeconds: number): void {
  token = next;
  expiresAt = Date.now() + expiresInSeconds * 1000;
  version += 1;
  getChannel()?.postMessage({ type: "token", token, expiresAt } satisfies Message);
}

function refresh(): Promise<RefreshResult> {
  if (inflight) return inflight;
  const seen = version;
  getChannel(); // listen for other tabs before waiting on the lock
  const run = withLock(async (): Promise<RefreshResult> => {
    // Another tab (or an earlier caller) already produced a fresh token while we waited.
    if (version !== seen && token && Date.now() < expiresAt) return { ok: true, token };
    let response: Response;
    try {
      response = await fetch(REFRESH_URL, { method: "POST", credentials: "same-origin" });
    } catch {
      return { ok: false, reason: "network" };
    }
    if (response.status === 401 || response.status === 403) return { ok: false, reason: "denied" };
    if (!response.ok) return { ok: false, reason: "network" };
    const body = (await response.json()) as { access_token: string; expires_in: number };
    setToken(body.access_token, body.expires_in);
    return { ok: true, token: body.access_token };
  }).finally(() => {
    inflight = null;
  });
  inflight = run;
  return run;
}

export const session = {
  /** The current access token, or null when signed out. */
  getToken: (): string | null => token,

  /** Store the token from a successful login. */
  start(accessToken: string, expiresInSeconds: number): void {
    setToken(accessToken, expiresInSeconds);
  },

  refresh,

  /** A token fit to send now: refreshed first when it is about to expire. */
  async tokenForRequest(): Promise<string | null> {
    if (!token) return null;
    if (expiresAt - Date.now() > EARLY_REFRESH_MS) return token;
    const result = await refresh();
    return result.ok ? result.token : token; // let the server decide if it is really expired
  },

  /** Forget the session here and in every other tab (sign out, or the refresh was refused). */
  end(): void {
    token = null;
    expiresAt = 0;
    version += 1;
    getChannel()?.postMessage({ type: "logout" } satisfies Message);
  },

  /** The session is gone and cannot be revived: the app must show the sign-in page. */
  expire(): void {
    session.end();
    expiredListeners.forEach((listener) => listener());
  },

  onExpired(listener: () => void): () => void {
    getChannel();
    expiredListeners.add(listener);
    return () => expiredListeners.delete(listener);
  },
};

/** Test helper: back to a clean, signed-out state. */
export function resetSessionForTests(): void {
  token = null;
  expiresAt = 0;
  version = 0;
  inflight = null;
  expiredListeners.clear();
  channel?.close();
  channel = null;
}
