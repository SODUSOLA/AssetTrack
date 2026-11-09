/** One error type for everything that can go wrong talking to the API. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** The browser could not reach the server at all (offline, timeout, DNS). */
  get isNetwork(): boolean {
    return this.status === 0;
  }

  /** Validation messages by field name, from a `422 VALIDATION_ERROR`. */
  get fieldErrors(): Record<string, string> {
    const list = this.details.errors;
    const out: Record<string, string> = {};
    if (!Array.isArray(list)) return out;
    for (const entry of list) {
      if (typeof entry !== "object" || entry === null) continue;
      const { loc, msg } = entry as { loc?: unknown; msg?: unknown };
      if (!Array.isArray(loc) || typeof msg !== "string") continue;
      const field = [...loc].reverse().find((part) => typeof part === "string" && part !== "body");
      if (typeof field === "string" && !(field in out)) out[field] = msg;
    }
    return out;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

/** Build an ApiError from a response status and its (already parsed) JSON body. */
export function apiErrorFrom(status: number, body: unknown): ApiError {
  const error = (body as { error?: unknown } | null | undefined)?.error;
  if (typeof error === "object" && error !== null) {
    const { code, message, details } = error as Record<string, unknown>;
    return new ApiError(
      status,
      typeof code === "string" ? code : `HTTP_${status}`,
      typeof message === "string" ? message : "Something went wrong.",
      typeof details === "object" && details !== null ? (details as Record<string, unknown>) : {},
    );
  }
  return new ApiError(status, `HTTP_${status}`, "Something went wrong.");
}

export async function errorFromResponse(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.clone().json();
  } catch {
    /* not JSON */
  }
  return apiErrorFrom(response.status, body);
}

export function networkError(cause: unknown): ApiError {
  if (isApiError(cause)) return cause;
  const name = cause instanceof DOMException || cause instanceof Error ? cause.name : "";
  if (name === "TimeoutError") {
    return new ApiError(0, "TIMEOUT", "The server took too long to answer.");
  }
  if (name === "AbortError") {
    return new ApiError(0, "ABORTED", "The request was cancelled.");
  }
  return new ApiError(0, "NETWORK_ERROR", "Cannot reach the server. Check your connection.");
}
