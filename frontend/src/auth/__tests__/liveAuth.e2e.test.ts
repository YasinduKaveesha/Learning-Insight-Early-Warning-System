import { createClient } from "@supabase/supabase-js";
import { describe, expect, it } from "vitest";

// frontend_plan §11.0 gates 7-8 — these need a LIVE backend and a real
// teacher01 credential, NEITHER OF WHICH EXISTS YET. They are committed so
// they run the moment the env vars are set, and skip cleanly until then.
//
//   T3_E2E_SUPABASE_URL, T3_E2E_SUPABASE_ANON_KEY,
//   T3_E2E_TEACHER_EMAIL, T3_E2E_TEACHER_PASSWORD
//
// Gate 7: sign in as teacher01 -> a valid session (the app then lands Home).
// Gate 8: two independent clients sign in AT THE SAME TIME, both succeed —
//         the failure anonymous sign-in (D29) would have produced.

const env = process.env;
const READY = Boolean(
  env.T3_E2E_SUPABASE_URL &&
    env.T3_E2E_SUPABASE_ANON_KEY &&
    env.T3_E2E_TEACHER_EMAIL &&
    env.T3_E2E_TEACHER_PASSWORD,
);

function freshClient() {
  return createClient(env.T3_E2E_SUPABASE_URL as string, env.T3_E2E_SUPABASE_ANON_KEY as string, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

describe.skipIf(!READY)("live auth gates (require T3_E2E_* env)", () => {
  it("gate 7: teacher01 signs in and gets a usable access token", async () => {
    const { data, error } = await freshClient().auth.signInWithPassword({
      email: env.T3_E2E_TEACHER_EMAIL as string,
      password: env.T3_E2E_TEACHER_PASSWORD as string,
    });
    expect(error).toBeNull();
    expect(data.session?.access_token).toBeTruthy();
  });

  it("gate 8: two concurrent sessions both succeed (D29 — no demo-pool lockout)", async () => {
    const [a, b] = await Promise.all([
      freshClient().auth.signInWithPassword({
        email: env.T3_E2E_TEACHER_EMAIL as string,
        password: env.T3_E2E_TEACHER_PASSWORD as string,
      }),
      freshClient().auth.signInWithPassword({
        email: env.T3_E2E_TEACHER_EMAIL as string,
        password: env.T3_E2E_TEACHER_PASSWORD as string,
      }),
    ]);
    expect(a.error).toBeNull();
    expect(b.error).toBeNull();
    expect(a.data.session?.access_token).toBeTruthy();
    expect(b.data.session?.access_token).toBeTruthy();
  });
});
