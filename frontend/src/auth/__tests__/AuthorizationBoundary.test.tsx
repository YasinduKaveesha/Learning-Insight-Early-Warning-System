import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthorizationBoundary } from "../AuthorizationBoundary";
import { apiError } from "../../lib/apiError";

const signOut = vi.fn(async () => {});
vi.mock("../SessionProvider", () => ({
  useSession: () => ({
    status: "authenticated",
    session: { user: { email: "learner.account@example.com" } },
    isAuthed: true,
    signIn: vi.fn(),
    signOut,
  }),
}));

/** A screen that does what every real screen does: one query through the client. */
function Screen({ fail }: { fail: unknown | null }) {
  const { data } = useQuery({
    queryKey: ["home"],
    queryFn: () => (fail ? Promise.reject(fail) : Promise.resolve("the dashboard")),
  });
  return <div>{data ?? "loading"}</div>;
}

function renderWith(fail: unknown | null, queryClient = freshClient()) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={
              <AuthorizationBoundary>
                <Screen fail={fail} />
              </AuthorizationBoundary>
            }
          />
          <Route path="/login" element={<div>Login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function freshClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
}

beforeEach(() => signOut.mockClear());

describe("AuthorizationBoundary — a 403 is about the caller, not the screen", () => {
  it("replaces the screen when any query is refused with 403", async () => {
    renderWith(apiError("/home", 403));
    await waitFor(() =>
      expect(screen.getByText(/can.t open the dashboard/i)).toBeInTheDocument(),
    );
  });

  it("names the signed-in address, because the wrong account is the usual cause", async () => {
    renderWith(apiError("/home", 403));
    await waitFor(() =>
      expect(screen.getByText("learner.account@example.com")).toBeInTheDocument(),
    );
  });

  it("offers NO retry — the same request would be refused the same way", async () => {
    renderWith(apiError("/home", 403));
    await waitFor(() => expect(screen.getByRole("button", { name: /log out/i })).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /try again/i })).not.toBeInTheDocument();
  });

  it("never says to check the connection — that advice cannot work for a 403", async () => {
    renderWith(apiError("/home", 403));
    await waitFor(() => expect(screen.getByRole("button", { name: /log out/i })).toBeInTheDocument());
    expect(screen.queryByText(/check your connection/i)).not.toBeInTheDocument();
  });

  it("logging out clears the session AND the cache, then lands on /login", async () => {
    const queryClient = freshClient();
    renderWith(apiError("/home", 403), queryClient);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /log out/i })).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /log out/i }));

    await waitFor(() => expect(screen.getByText("Login screen")).toBeInTheDocument());
    expect(signOut).toHaveBeenCalledOnce();
    // The refused query must not survive — it would block the next sign-in here.
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  });

  it("leaves every other failure to the screen's own ErrorState", async () => {
    renderWith(apiError("/home", 500));
    await waitFor(() => expect(screen.getByText("loading")).toBeInTheDocument());
    expect(screen.queryByText(/can.t open the dashboard/i)).not.toBeInTheDocument();
  });

  it("renders the screen normally when nothing is refused", async () => {
    renderWith(null);
    await waitFor(() => expect(screen.getByText("the dashboard")).toBeInTheDocument());
    expect(screen.queryByText(/can.t open the dashboard/i)).not.toBeInTheDocument();
  });

  it("catches a 403 that settled BEFORE it mounted — a prefetch from the last screen", async () => {
    const queryClient = freshClient();
    // No further cache event will fire for this; only the mount-time check sees it.
    await queryClient
      .fetchQuery({ queryKey: ["prefetched"], queryFn: () => Promise.reject(apiError("/watch", 403)) })
      .catch(() => {});

    renderWith(null, queryClient);
    await waitFor(() =>
      expect(screen.getByText(/can.t open the dashboard/i)).toBeInTheDocument(),
    );
  });
});
