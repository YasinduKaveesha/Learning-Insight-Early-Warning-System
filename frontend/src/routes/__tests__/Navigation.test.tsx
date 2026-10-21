import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../../App";

// A session the CompD sign-in test (U11) can sign out. Every other test here runs
// signed in, exactly as the real mock-mode SessionProvider would have them.
const session = vi.hoisted(() => ({ authed: true }));
vi.mock("../../auth/SessionProvider", async () => {
  const actual = await vi.importActual<typeof import("../../auth/SessionProvider")>(
    "../../auth/SessionProvider",
  );
  return {
    ...actual,
    SessionProvider: ({ children }: { children: ReactNode }) => children,
    useSession: () => ({
      status: session.authed ? "mock" : "unauthenticated",
      session: null,
      isAuthed: session.authed,
      signIn: async () => {
        session.authed = true;
        return null;
      },
      signUp: async () => ({ ok: true, needsConfirmation: false }),
      signOut: async () => {
        session.authed = false;
      },
    }),
  };
});

afterEach(() => {
  session.authed = true;
});

/**
 * Navigation, against the REAL route table in App.tsx (the test environment runs
 * on the mock client with no Supabase project, so the route guard lets it through).
 *
 * The All Classes page (/classes) was removed on 2026-09-14. A teacher could land
 * on it by pressing Back quickly, because every back button fell back to /classes
 * while its page was still loading. These tests pin both halves of the fix.
 */

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <App />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Navigation — the removed /classes page", () => {
  it("/classes redirects to Home instead of showing a page that no longer exists", async () => {
    renderAt("/classes");
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(/^\/$/));
  });
});

describe("Navigation — no screen links to /classes", () => {
  it("no source file routes anywhere to the bare /classes path except the redirect itself", async () => {
    // A source scan, because the bug was a fallback in a ternary that only ran
    // while data was loading -- exactly the branch a rendered test rarely sees.
    const { readdirSync, readFileSync, statSync } = await import("node:fs");
    const { join, resolve, dirname } = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../");

    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir)) {
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) {
          if (entry !== "__tests__") walk(full);
          continue;
        }
        if (!/\.(ts|tsx)$/.test(entry)) continue;
        const text = readFileSync(full, "utf-8");
        // Matches "/classes" as a whole string literal, not /classes/:classId.
        if (/["'`]\/classes["'`]/.test(text) && !full.endsWith("App.tsx")) offenders.push(full);
      }
    };
    walk(root);
    expect(offenders).toEqual([]);
  });
});

describe("Navigation — the CompD pages through sign-in (D-028, U11)", () => {
  function FullLocationProbe() {
    const location = useLocation();
    return <div data-testid="full-location">{`${location.pathname}${location.search}${location.hash}`}</div>;
  }

  function renderSignedOutAt(path: string) {
    session.authed = false;
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>
          <App />
          <FullLocationProbe />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  async function signIn() {
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "teacher@example.test");
    await user.type(screen.getByLabelText("Password"), "a-long-enough-password");
    await user.click(screen.getByRole("button", { name: "Log in" }));
  }

  it.each([
    ["/compd?tab=questions", "/compd"],
    ["/compd/students/STU-0001#history", "/compd/students/STU-0001"],
  ])("%s redirects to sign-in, then returns to the same PATH (Q16 (a): not the ?tab or #)", async (start, back) => {
    renderSignedOutAt(start);
    await waitFor(() => expect(screen.getByTestId("full-location")).toHaveTextContent(/^\/login$/));
    await signIn();
    await waitFor(() => expect(screen.getByTestId("full-location").textContent).toBe(back));
  });
});
