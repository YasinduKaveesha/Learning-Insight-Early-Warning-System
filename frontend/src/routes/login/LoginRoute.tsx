import { useState } from "react";
import type { FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useSession } from "../../auth/SessionProvider";
import type { AuthFailure } from "../../auth/authErrors";

/**
 * The login screen (frontend_plan §11.0). One email/password form and
 * nothing else — no sign-up, no password reset, no "remember me". The
 * dashboard provisions no accounts; identity belongs to the student app
 * (D3). Email/password sign-in only (D29).
 *
 * A login screen is a screen: 44px targets, real <label>s, visible focus,
 * a live-region error, mobile-first at 375px.
 */
interface FromState {
  from?: string;
}

export default function LoginRoute() {
  const { signIn } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as FromState | null)?.from ?? "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting">("idle");
  const [failure, setFailure] = useState<AuthFailure | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (status === "submitting") return;
    setFailure(null);
    setStatus("submitting");
    try {
      const result = await signIn(email, password);
      if (result) {
        setFailure(result);
        setStatus("idle");
        return;
      }
      navigate(from, { replace: true });
    } catch {
      // signIn already maps known Supabase errors; anything reaching here is
      // unexpected. Never surface the raw error.
      setFailure({
        kind: "unknown",
        message: "Something went wrong while signing you in. Please try again in a moment.",
        retryable: true,
      });
      setStatus("idle");
    }
  }

  const submitting = status === "submitting";

  return (
    <div className="mx-auto flex min-h-screen max-w-[480px] flex-col justify-center gap-6 p-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-subtitle font-extrabold text-ink-primary">Teacher sign in</h1>
        <p className="text-sm text-ink-secondary">
          Sign in with the email and password for your school's account.
        </p>
      </div>

      <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
        <div className="flex flex-col gap-1">
          <label htmlFor="login-email" className="text-sm font-bold text-ink-primary">
            Email
          </label>
          <input
            id="login-email"
            name="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="min-h-[44px] rounded-lg border border-border-strong bg-surface1 px-3 text-base text-ink-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="login-password" className="text-sm font-bold text-ink-primary">
            Password
          </label>
          <input
            id="login-password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="min-h-[44px] rounded-lg border border-border-strong bg-surface1 px-3 text-base text-ink-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          />
        </div>

        {/* Always in the DOM as a live region so a screen reader announces
            the failure when it appears; empty and invisible until then. */}
        <div role="alert" aria-live="assertive">
          {failure ? (
            <p className="rounded-lg border border-danger bg-danger-soft p-3 text-sm text-danger-text">
              {failure.message}
            </p>
          ) : null}
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="min-h-[44px] rounded-lg bg-foreground px-4 text-sm font-bold text-surface1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring disabled:opacity-60"
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
