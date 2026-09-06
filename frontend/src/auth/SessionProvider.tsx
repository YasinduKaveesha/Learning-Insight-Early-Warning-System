// Session context (frontend_plan §11.0). Holds the Supabase session, keeps
// it in sync across refresh and token-refresh events, and exposes sign-in /
// sign-out. This is the only place the app reads auth state.

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { isSupabaseConfigured, supabase } from "../api/supabaseClient";
import { classifySignInError, type AuthFailure } from "./authErrors";

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

export interface SessionContextValue {
  status: SessionStatus;
  session: Session | null;
  /** True when the route guard should allow protected routes. */
  isAuthed: boolean;
  /** Resolves to null on success, or an AuthFailure to render. */
  signIn: (email: string, password: string) => Promise<AuthFailure | null>;
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
