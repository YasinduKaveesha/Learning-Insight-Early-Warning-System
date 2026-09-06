// Supabase auth client (frontend_plan §11.0). This file owns ONE thing:
// turning env config into a Supabase client, or into `null` when auth is
// not configured. It produces a TOKEN and a SESSION — nothing consumes them
// here (that is B6.3e-2's httpClient).
//
// Email/password sign-in ONLY — decision D29. Anonymous sign-in is never
// used: t3_teacher_bindings.teacher_profile_id is UNIQUE, so a single demo
// teacher means the first anonymous session claims them and every later one
// gets 409 demo_pool_exhausted with no recovery.

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url: string | undefined = import.meta.env.VITE_SUPABASE_URL;
const anonKey: string | undefined = import.meta.env.VITE_SUPABASE_ANON_KEY;

// VITE_USE_MOCK=true (or no Supabase env at all) => the whole app runs
// against MockClient with NO Supabase project configured. This is the
// rollback path and frontend_plan §11.0 gate 5.
const useMock = import.meta.env.VITE_USE_MOCK === "true";

/** True only when a real Supabase project is wired up AND the mock path is
 * not forced. When false, the route guard lets every request through so the
 * demo path survives without an auth backend. */
export const isSupabaseConfigured: boolean = Boolean(url) && Boolean(anonKey) && !useMock;

export const supabase: SupabaseClient | null = isSupabaseConfigured
  ? createClient(url as string, anonKey as string, {
      auth: {
        // Persist the session so a page refresh does not sign the teacher
        // out, and refresh the access token before it expires — a silently
        // expired token surfaces as a wall of 401s that look like an outage
        // (frontend_plan §11.0).
        persistSession: true,
        autoRefreshToken: true,
        // The dashboard has no OAuth redirect flow; nothing to parse.
        detectSessionInUrl: false,
      },
    })
  : null;
