import { useState } from "react";
import type { FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useSession } from "../../auth/SessionProvider";
import type { AuthFailure } from "../../auth/authErrors";

/**
 * Sign in, or create a teacher account (frontend_plan §11.0, B6.4).
 *
 * Two tabs on one card, the shape the student app uses for the same job, in
 * this dashboard's own palette and on the same MathMingo wordmark.
 *
 * CREATING AN ACCOUNT IS TWO STEPS, and the second is the one that is easy to
 * forget: a Supabase identity alone is not a teacher. `SessionProvider.signUp`
 * also asks the STUDENT APP to create the `teacher_profiles` row (D3 — only it
 * may write one). Without that the dashboard answers 403 to everything, which
 * reads to a teacher as "my login is broken".
 *
 * THE CREATE FORM IS SPLIT ACROSS TWO SCREENS, copying the student app's own
 * reasoning: each screen shows at most the two fields log in shows, so the card
 * never grows taller when the teacher switches tab. Name and email first, then
 * password and its confirmation.
 *
 * Name and email are all that is collected, plus the password Supabase needs.
 * No gender, no school, no role picker: the dashboard has no use for them, and
 * a field with no consumer is a question asked for nothing.
 *
 * A login screen is a screen: 44px targets, real <label>s, visible focus, a
 * live-region message, mobile-first at 375px.
 */
interface FromState {
  from?: string;
}

type Tab = "signin" | "create";
type CreateStep = 1 | 2;

const FIELD =
  "min-h-[44px] rounded-lg border border-border-strong bg-surface1 px-3 text-base text-ink-primary " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring";

const MIN_PASSWORD_LENGTH = 8;

export default function LoginRoute() {
  const { signIn, signUp } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as FromState | null)?.from ?? "/";

  const [tab, setTab] = useState<Tab>("signin");
  const [step, setStep] = useState<CreateStep>(1);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting">("idle");
  const [failure, setFailure] = useState<AuthFailure | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const submitting = status === "submitting";
  const creating = tab === "create";

  // The button says what it will do, and is disabled until it can do it --
  // rather than accepting a click and answering with a validation error.
  const stepOneReady = name.trim().length >= 2 && email.trim().length > 0;
  const stepTwoReady =
    password.length >= MIN_PASSWORD_LENGTH && confirmPassword.length >= MIN_PASSWORD_LENGTH;
  const ready = creating
    ? step === 1
      ? stepOneReady
      : stepTwoReady
    : email.trim().length > 0 && password.length > 0;

  function switchTab(next: Tab) {
    setTab(next);
    setStep(1);
    setFailure(null);
    setNotice(null);
    setPassword("");
    setConfirmPassword("");
  }

  function resetAfterSignUp() {
    setStep(1);
    setPassword("");
    setConfirmPassword("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting || !ready) return;
    setFailure(null);
    setNotice(null);

    // Step 1 of create is a step, not a submission: nothing is sent yet.
    if (creating && step === 1) {
      setStep(2);
      return;
    }

    if (creating && password !== confirmPassword) {
      // Checked here rather than by disabling the button: "the passwords do not
      // match" is something the teacher needs told, not silently enforced.
      setFailure({
        kind: "weak_password",
        message: "The passwords do not match.",
        retryable: true,
      });
      return;
    }

    setStatus("submitting");
    try {
      if (creating) {
        const result = await signUp(name, email, password);
        if (!result.ok) {
          setFailure(result.failure);
          setStatus("idle");
          return;
        }
        if (result.needsConfirmation) {
          // No session yet, so there is nothing to sign into and no teacher
          // profile could be created. Say so plainly and leave them on log in.
          setTab("signin");
          resetAfterSignUp();
          setNotice("Account created. Check your email to confirm it, then log in.");
          setStatus("idle");
          return;
        }
      } else {
        const result = await signIn(email, password);
        if (result) {
          setFailure(result);
          setStatus("idle");
          return;
        }
      }
      navigate(from, { replace: true });
    } catch {
      // signIn/signUp map the errors they know. Anything reaching here is
      // unexpected, and the raw error is never surfaced.
      setFailure({
        kind: "unknown",
        message: "Something went wrong. Please try again in a moment.",
        retryable: true,
      });
      setStatus("idle");
    }
  }

  const heading = !creating
    ? "Welcome back"
    : step === 1
      ? "Create your account"
      : "Choose a password";
  const subheading = !creating
    ? "Log in to see how your classes are getting on."
    : step === 1
      ? "Your name and email are all we need."
      : `At least ${MIN_PASSWORD_LENGTH} characters.`;
  const primaryLabel = submitting
    ? creating
      ? "Creating your account…"
      : "Signing in…"
    : creating
      ? step === 1
        ? "Next"
        : "Create account"
      : "Log in";

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto flex min-h-screen max-w-[480px] flex-col justify-center gap-6 p-4">
        <div className="flex justify-center">
          <img
            src="/mathmingo-header.png"
            alt="MathMingo"
            className="h-20 w-auto max-w-full object-contain"
          />
        </div>

        <div className="flex flex-col gap-5 rounded-lg border border-border bg-surface1 p-4">
          {/* Tabs, not two routes: the teacher can switch without losing the
              email they already typed. Real buttons, so keyboard and screen
              readers get them for free. */}
          <div
            role="tablist"
            aria-label="Log in or create an account"
            className="grid grid-cols-2 gap-2 rounded-lg bg-primary-soft p-1"
          >
            {(["signin", "create"] as const).map((value) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={tab === value}
                onClick={() => switchTab(value)}
                className={`min-h-[44px] rounded-lg px-3 text-sm font-bold ${
                  tab === value ? "bg-surface1 text-ink-primary shadow-sm" : "text-ink-secondary"
                }`}
              >
                {value === "signin" ? "Log in" : "Create"}
              </button>
            ))}
          </div>

          <div className="flex flex-col gap-1">
            <h1 className="text-lg font-extrabold text-ink-primary">{heading}</h1>
            <p className="text-sm text-ink-secondary">{subheading}</p>
          </div>

          <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
            {creating && step === 1 ? (
              <div className="flex flex-col gap-1">
                <label htmlFor="signup-name" className="text-sm font-bold text-ink-primary">
                  Your name
                </label>
                <input
                  id="signup-name"
                  name="name"
                  type="text"
                  autoComplete="name"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Ms Perera"
                  className={FIELD}
                />
              </div>
            ) : null}

            {!creating || step === 1 ? (
              <div className="flex flex-col gap-1">
                <label htmlFor="login-email" className="text-sm font-bold text-ink-primary">
                  Email
                </label>
                <input
                  id="login-email"
                  name="email"
                  type="email"
                  autoComplete={creating ? "email" : "username"}
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="teacher@example.com"
                  className={FIELD}
                />
              </div>
            ) : null}

            {!creating || step === 2 ? (
              <div className="flex flex-col gap-1">
                <label htmlFor="login-password" className="text-sm font-bold text-ink-primary">
                  Password
                </label>
                <input
                  id="login-password"
                  name="password"
                  type="password"
                  autoComplete={creating ? "new-password" : "current-password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={creating ? "Create a password" : "Enter your password"}
                  className={FIELD}
                />
              </div>
            ) : null}

            {creating && step === 2 ? (
              <div className="flex flex-col gap-1">
                <label htmlFor="signup-confirm" className="text-sm font-bold text-ink-primary">
                  Confirm password
                </label>
                <input
                  id="signup-confirm"
                  name="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Type it again"
                  className={FIELD}
                />
              </div>
            ) : null}

            {/* Always in the DOM as a live region so a screen reader announces a
                message when it appears; empty and invisible until then. */}
            <div role="alert" aria-live="assertive">
              {failure ? (
                <p className="rounded-lg border border-danger bg-danger-soft p-3 text-sm text-danger-text">
                  {failure.message}
                </p>
              ) : notice ? (
                <p className="rounded-lg border border-secondary bg-secondary-soft p-3 text-sm text-secondary-foreground">
                  {notice}
                </p>
              ) : null}
            </div>

            <button
              type="submit"
              disabled={submitting || !ready}
              className="min-h-[44px] rounded-lg bg-foreground px-4 text-sm font-bold text-surface1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring disabled:opacity-60"
            >
              {primaryLabel}
            </button>

            {creating && step === 2 ? (
              <button
                type="button"
                onClick={() => {
                  setStep(1);
                  setFailure(null);
                }}
                disabled={submitting}
                className="min-h-[44px] rounded-lg border border-border-strong px-4 text-sm font-semibold text-ink-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring disabled:opacity-60"
              >
                Back
              </button>
            ) : null}
          </form>
        </div>
      </div>
    </div>
  );
}
