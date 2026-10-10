// Typed API failures (added 2026-10-08).
//
// WHY THIS EXISTS. `httpClient` used to collapse every non-OK response into a
// single untyped `Error`, so every screen rendered the same ErrorState: "Check
// your connection and try again." That is true of a network failure and false
// of a 403 -- the backend's own word for "your token is fine and you are still
// not a teacher here" (see the backend's `current_principal`). Telling a
// teacher to check their connection and retry, when retrying can never work,
// is worse than saying nothing: it hides the only thing they could act on.
//
// So the status survives the throw. `NotAuthorizedError` is the one case the
// app handles specially; everything else stays a plain retryable failure and
// renders exactly as it did before.

/** Any non-2xx from the dashboard backend. The message is unchanged from the
 * untyped version it replaces, so nothing that matched on it has to change. */
export class ApiRequestError extends Error {
  readonly status: number;
  readonly path: string;
  constructor(path: string, status: number) {
    super(`Request to ${path} failed with HTTP ${status}`);
    this.name = "ApiRequestError";
    this.status = status;
    this.path = path;
  }
}

/** HTTP 403: the token verified and the subject is not an authorized teacher.
 * Never retryable -- a retry sends the same token to the same check. */
export class NotAuthorizedError extends ApiRequestError {
  readonly code = "NOT_AUTHORIZED" as const;
  constructor(path: string) {
    super(path, 403);
    this.name = "NotAuthorizedError";
  }
}

/** The single place a status becomes an error object. */
export function apiError(path: string, status: number): ApiRequestError {
  return status === 403 ? new NotAuthorizedError(path) : new ApiRequestError(path, status);
}

/** Duck-typed like `isRecommendationConflictError`, so an error that crossed a
 * module or bundle boundary still matches (`instanceof` would not). */
export function isNotAuthorizedError(e: unknown): e is NotAuthorizedError {
  return (
    typeof e === "object" &&
    e !== null &&
    "code" in e &&
    (e as { code: unknown }).code === "NOT_AUTHORIZED"
  );
}
