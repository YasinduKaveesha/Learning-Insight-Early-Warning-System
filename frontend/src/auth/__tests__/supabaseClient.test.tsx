import { describe, expect, it } from "vitest";
import { isSupabaseConfigured, supabase } from "../../api/supabaseClient";
import { useSession } from "../SessionProvider";
import { render, screen } from "@testing-library/react";
import { SessionProvider } from "../SessionProvider";

// frontend_plan §11.0 gate 5 / §11.1 gate 3: with no Supabase env (and no
// VITE_USE_MOCK override needed), the whole app still runs with NO Supabase
// project configured. The test environment sets none of VITE_SUPABASE_*, so
// this is the rollback path exercised directly.
describe("no Supabase project configured -> rollback path holds", () => {
  it("isSupabaseConfigured is false and the client is null", () => {
    expect(isSupabaseConfigured).toBe(false);
    expect(supabase).toBeNull();
  });

  it("SessionProvider reports 'mock' status and lets requests through", () => {
    function Probe() {
      const { status, isAuthed } = useSession();
      return <div>{`${status}:${isAuthed}`}</div>;
    }
    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    );
    expect(screen.getByText("mock:true")).toBeInTheDocument();
  });
});
