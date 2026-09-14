// Session context (frontend_plan §11.0). Holds the Supabase session, keeps
// it in sync across refresh and token-refresh events, and exposes sign-in /
// sign-out. This is the only place the app reads auth state.

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { createTeacherProfile } from "../api/studentAppClient";
import { isSupabaseConfigured, supabase } from "../api/supabaseClient";
import { authFailure, classifySignInError, classifySignUpError } from "./authErrors";
import type { AuthFailure } from "./authErrors";

export type SessionStatus =
  // resolving getSession() on first load
  | "loading"
  // Supabase configured, a session is present
  | "authenticated"
  // Supabase configured, no session
  | "unauthenticated"
  // no Supabase project configured (VITE_USE_MOCK or missing env) — the
  // whole app runs anyway; the guard treats this as "let through"
  | "mock";

export type SignUpResult =
  | { ok: true; needsConfirmation: boolean }
  | { ok: false; failure: AuthFailure };

export interface SessionContextValue {
  status: SessionStatus;
  session: Session | null;
  /** True when the route guard should allow protected routes. */
  isAuthed: boolean;
  /** Resolves to null on success, or an AuthFailure to render. */
  signIn: (email: string, password: string) => Promise<AuthFailure | null>;
  /** Create a teacher account: a Supabase identity AND the student app's
   * teacher profile, which the dashboard requires (D3). See signUp below. */
  signUp: (name: string, email: string, password: string) => Promise<SignUpResult>;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<SessionStatus>(
    isSupabaseConfigured ? "loading" : "mock",
  );

  useEffect(() => {
    if (!supabase) return;
    let active = true;

    void supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      setSession(data.session);
      setStatus(data.session ? "authenticated" : "unauthenticated");
    });

    // Fires on SIGNED_IN, SIGNED_OUT and TOKEN_REFRESHED — the last is how
    // the pre-expiry refresh keeps `session` (and any consumer) current.
    const { data: listener } = supabase.auth.onAuthStateChange((_event, next) => {
      if (!active) return;
      setSession(next);
      setStatus(next ? "authenticated" : "unauthenticated");
    });

    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({
      status,
      session,
      isAuthed: status === "authenticated" || status === "mock",
      async signIn(email, password) {
        if (!supabase) return null;
        const { error } = await supabase.auth.signInWithPassword({
          email: email.trim(),
          password,
        });
        if (error) {
          return classifySignInError(error as { status?: number; message?: string });
        }
        return null;
      },
      async signUp(name, email, password) {
        if (!supabase) return { ok: true, needsConfirmation: false };

        const trimmedName = name.trim();
        const { data, error } = await supabase.auth.signUp({
          email: email.trim(),
          password,
          // Stored on the Supabase user as well, so the name survives even if the
          // teacher-profile call below fails and has to be retried.
          options: { data: { name: trimmedName } },
        });
        if (error) {
          return { ok: false, failure: classifySignUpError(error as { status?: number; message?: string }) };
        }

        // No session means the project requires email confirmation: there is no
        // token yet, so the teacher profile cannot be created until they sign in.
        if (!data.session) return { ok: true, needsConfirmation: true };

        try {
          // A Supabase identity alone is not a teacher. Without this the dashboard
          // answers 403 to everything, which reads as a broken login.
          await createTeacherProfile(trimmedName);
        } catch {
          return { ok: false, failure: authFailure("profile_setup_failed") };
        }
        return { ok: true, needsConfirmation: false };
      },
      async signOut() {
        if (supabase) await supabase.auth.signOut();
      },
    }),
    [status, session],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error("useSession must be used within <SessionProvider>");
  }
  return ctx;
}
