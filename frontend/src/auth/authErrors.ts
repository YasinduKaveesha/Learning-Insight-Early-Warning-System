// The three auth failures read DIFFERENTLY and are never collapsed into one
// "login failed" (frontend_plan §11.0):
//
//   401  -> token bad or expired; sign in again.
//   403  -> token is valid, this subject is not a teacher here. A message,
//           not a retry loop.
//   409 stage "demo_pool" -> should be unreachable under D29; if it shows,
//           T3_DEMO_MODE is on when it should be off. Say that; do not retry.
//
// Nothing here renders the token, the `sub`, or a raw backend error string.
// The backend deliberately collapses every verification failure into one
// claim-free message; this module does not undo that.

export type AuthFailureKind =
  | "bad_credentials"
  | "token_invalid"
  | "not_a_teacher"
  | "demo_mode_on"
  | "unknown";

export interface AuthFailure {
  kind: AuthFailureKind;
  /** Plain language, safe to render. Never contains a token, a subject id,
   * a status code, or a backend error string. */
  message: string;
  /** Whether re-entering the password could plausibly help. 403 / demo-mode
   * are not the teacher's fault, so the form should not invite a retry. */
  retryable: boolean;
}

const FAILURES: Record<AuthFailureKind, Omit<AuthFailure, "kind">> = {
  bad_credentials: {
    message: "That email and password don't match. Check them and try again.",
    retryable: true,
  },
  token_invalid: {
    message: "Your session has expired. Please sign in again.",
    retryable: true,
  },
  not_a_teacher: {
    message:
      "This account is not set up as a teacher on this dashboard. Ask whoever manages your school's account to add you.",
    retryable: false,
  },
  demo_mode_on: {
    message:
      "The dashboard is running in demo mode when it should not be. Ask an administrator to turn that off, then sign in again.",
    retryable: false,
  },
  unknown: {
    message: "Something went wrong while signing you in. Please try again in a moment.",
    retryable: true,
  },
};

export function authFailure(kind: AuthFailureKind): AuthFailure {
  return { kind, ...FAILURES[kind] };
}

function stageOf(body: unknown): string | undefined {
  if (body && typeof body === "object" && "stage" in body) {
    const stage = (body as { stage: unknown }).stage;
    return typeof stage === "string" ? stage : undefined;
  }
  return undefined;
}

/**
 * Classify a backend verification response (the request a real HttpClient
 * makes with the bearer token — B6.3e-2). Kept here, tested here, so the
 * three paths cannot silently collapse when that client is wired up.
 */
export function classifyVerificationResponse(status: number, body: unknown): AuthFailure {
  if (status === 401) return authFailure("token_invalid");
  if (status === 403) return authFailure("not_a_teacher");
  if (status === 409 && stageOf(body) === "demo_pool") return authFailure("demo_mode_on");
  return authFailure("unknown");
}

/**
 * Map a Supabase sign-in error to our vocabulary. Supabase answers a wrong
 * email/password with HTTP 400 and "Invalid login credentials".
 */
export function classifySignInError(
  error: { status?: number; message?: string } | null | undefined,
): AuthFailure {
  if (!error) return authFailure("unknown");
  if (error.status === 400 || /invalid login credentials/i.test(error.message ?? "")) {
    return authFailure("bad_credentials");
  }
  if (error.status === 401) return authFailure("token_invalid");
  if (error.status === 403) return authFailure("not_a_teacher");
  return authFailure("unknown");
}
