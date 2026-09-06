import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SessionContextValue, SessionStatus } from "../SessionProvider";

const sessionValue = vi.fn<() => SessionContextValue>();
vi.mock("../SessionProvider", () => ({
  useSession: () => sessionValue(),
}));

const { RedirectIfAuthed, RequireAuth } = await import("../RouteGuard");

function setSession(status: SessionStatus) {
  sessionValue.mockReturnValue({
    status,
    session: null,
    isAuthed: status === "authenticated" || status === "mock",
    signIn: vi.fn(),
    signOut: vi.fn(),
  });
}

function renderApp(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="/login"
          element={
            <RedirectIfAuthed>
              <div>Login screen</div>
            </RedirectIfAuthed>
          }
        />
        <Route
          path="/"
          element={
            <RequireAuth>
              <div>Home screen</div>
            </RequireAuth>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => sessionValue.mockReset());

describe("RouteGuard (frontend_plan §11.0)", () => {
  it("unauthenticated -> redirected from a protected route to /login", () => {
    setSession("unauthenticated");
    renderApp("/");
    expect(screen.getByText("Login screen")).toBeInTheDocument();
    expect(screen.queryByText("Home screen")).not.toBeInTheDocument();
  });

  it("authenticated while on /login -> redirected home", () => {
    setSession("authenticated");
    renderApp("/login");
    expect(screen.getByText("Home screen")).toBeInTheDocument();
  });

  it("authenticated -> protected route renders", () => {
    setSession("authenticated");
    renderApp("/");
    expect(screen.getByText("Home screen")).toBeInTheDocument();
  });

  it("loading -> neither screen; a skeleton holds the page", () => {
    setSession("loading");
    renderApp("/");
    expect(screen.queryByText("Home screen")).not.toBeInTheDocument();
    expect(screen.queryByText("Login screen")).not.toBeInTheDocument();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("mock (no Supabase project configured) -> app runs, protected routes pass", () => {
    setSession("mock");
    renderApp("/");
    expect(screen.getByText("Home screen")).toBeInTheDocument();
  });
});
