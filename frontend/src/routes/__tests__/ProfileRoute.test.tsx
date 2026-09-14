import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ProfileRoute from "../profile/ProfileRoute";
import { renderRoute } from "./testUtils";

vi.mock("../../api/client", () => ({
  client: {
    getHome: vi.fn(),
    getCohort: vi.fn(),
    getClassWatchList: vi.fn(),
    getWatchList: vi.fn(),
    getStudentOverview: vi.fn(),
    getStudentSessions: vi.fn(),
    getStudentRecommendations: vi.fn(),
    createClass: vi.fn(),
    getJoinRequests: vi.fn(),
    approveJoinRequest: vi.fn(),
    rejectJoinRequest: vi.fn(),
    getClassReports: vi.fn(),
  },
}));

const signOut = vi.fn(async () => {});
vi.mock("../../auth/SessionProvider", () => ({
  useSession: () => ({
    status: "authenticated",
    // The email row reads the signed-in Supabase user; the dashboard stores no copy.
    session: { user: { email: "ms.perera@example.com" } },
    isAuthed: true,
    signIn: vi.fn(),
    signOut,
  }),
}));

const { client } = await import("../../api/client");

const HOME_SUMMARY = {
  teacherName: "Ms Perera",
  studentsToWatch: 7,
  activeStudents: 83,
  classCount: 3,
  gettingStarted: 9,
  classes: [],
  disclosure: "Literature-informed synthetic data — not clinical evidence.",
};

function renderProfile() {
  return renderRoute(<ProfileRoute />, { path: "/profile", initialPath: "/profile" });
}

beforeEach(() => {
  vi.mocked(client.getHome).mockReset();
  signOut.mockClear();
});

describe("ProfileRoute — the teacher's own details, per plan §3", () => {
  it("shows the teacher's name, email, class count and student count, and a log-out button", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderProfile();
    // Once under the avatar, once in the Name row.
    await waitFor(() => expect(screen.getAllByText("Ms Perera")).toHaveLength(2));

    expect(screen.getByText("Email")).toBeInTheDocument();
    expect(screen.getByText("ms.perera@example.com")).toBeInTheDocument();
    expect(screen.getByText("Classes")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Students")).toBeInTheDocument();
    expect(screen.getByText("83")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
  });

  it("every row is a value the system already holds — no settings or preferences", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderProfile();
    await waitFor(() => expect(screen.getAllByText("Ms Perera").length).toBeGreaterThan(0));
    expect(screen.queryByText(/settings/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/preferences/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/edit/i)).not.toBeInTheDocument();
  });
});

describe("ProfileRoute — layout", () => {
  it("has no visible 'Profile' title, but keeps one for screen readers", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderProfile();
    await waitFor(() => expect(screen.getAllByText("Ms Perera")).toHaveLength(2));
    const heading = screen.getByRole("heading", { level: 1, name: "Profile" });
    expect(heading).toHaveClass("sr-only");
  });

  it("has a Home button in a bottom bar that links back to the dashboard", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderProfile();
    await waitFor(() => expect(screen.getAllByText("Ms Perera")).toHaveLength(2));
    const home = screen.getByRole("link", { name: "Home" });
    expect(home).toHaveAttribute("href", "/");
    expect(home.closest("nav")).toHaveAttribute("aria-label", "Profile navigation");
  });
});

describe("ProfileRoute — states", () => {
  it("loading renders a skeleton, not a spinner", () => {
    vi.mocked(client.getHome).mockReturnValue(new Promise(() => {}));
    renderProfile();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("error state says what failed and offers retry, never a raw error string", async () => {
    vi.mocked(client.getHome).mockRejectedValue(new Error("500 Internal Server Error"));
    renderProfile();
    await waitFor(() => expect(screen.getByText(/Couldn't load your profile/)).toBeInTheDocument());
    expect(screen.queryByText(/500/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("ProfileRoute — sign out (B6.3e-1 gate 5)", () => {
  it("clears the Supabase session AND the query cache, then lands on /login", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    // Seed the cache with a previous teacher's data.
    queryClient.setQueryData(["home"], HOME_SUMMARY);
    queryClient.setQueryData(["cohort", "class-1"], { some: "cohort" });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/profile"]}>
          <Routes>
            <Route path="/profile" element={<ProfileRoute />} />
            <Route path="/login" element={<div>Login screen</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findAllByText("Ms Perera");
    await userEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => expect(screen.getByText("Login screen")).toBeInTheDocument());
    expect(signOut).toHaveBeenCalledTimes(1);
    // Assert the CACHE, not just the redirect.
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(queryClient.getQueryData(["home"])).toBeUndefined();
    expect(queryClient.getQueryData(["cohort", "class-1"])).toBeUndefined();
  });
});
