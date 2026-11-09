import createClient from "openapi-fetch";
import { apiErrorFrom, errorFromResponse, networkError } from "./errors";
import type { paths } from "./schema";
import { session } from "./session";

const BASE = import.meta.env.VITE_API_BASE ?? "";
const REQUEST_TIMEOUT_MS = 30_000;

const NO_REFRESH = ["/auth/login", "/auth/refresh", "/auth/logout"];

function skipsRefresh(url: string): boolean {
  const path = new URL(url, "http://local").pathname;
  return NO_REFRESH.some((suffix) => path.endsWith(suffix));
}

function send(request: Request, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(new DOMException("The request timed out", "TimeoutError")),
    timeoutMs,
  );
  if (request.signal.aborted) controller.abort(request.signal.reason);
  request.signal.addEventListener("abort", () => controller.abort(request.signal.reason), {
    once: true,
  });
  return fetch(new Request(request, { signal: controller.signal })).finally(() =>
    clearTimeout(timer),
  );
}

/**
 * fetch with the bearer token, a timeout, and one silent refresh-and-retry on 401.
 * A refresh that is refused ends the session; the app then shows the sign-in page.
 */
export async function authedFetch(
  input: Request,
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const attempt = async (token: string | null) => {
    const request = input.clone(); // the body of a Request can be read only once
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return send(request, timeoutMs);
  };

  const first = await attempt(await session.tokenForRequest());
  if (first.status !== 401 || skipsRefresh(input.url)) return first;

  const result = await session.refresh();
  if (!result.ok) {
    if (result.reason === "denied") session.expire();
    return first;
  }
  return attempt(result.token);
}

/** Typed from the backend's OpenAPI document: an invented path or field does not compile. */
export const api = createClient<paths>({ baseUrl: BASE, fetch: (request) => authedFetch(request) });

type Result<T> = { data?: T; error?: unknown; response: Response };

/** Turn an openapi-fetch result into the data, or throw an ApiError. */
export async function unwrap<T>(pending: Promise<Result<T>>): Promise<T> {
  let result: Result<T>;
  try {
    result = await pending;
  } catch (cause) {
    throw networkError(cause);
  }
  if (result.error !== undefined) throw apiErrorFrom(result.response.status, result.error);
  if (!result.response.ok) throw await errorFromResponse(result.response);
  return result.data as T;
}
