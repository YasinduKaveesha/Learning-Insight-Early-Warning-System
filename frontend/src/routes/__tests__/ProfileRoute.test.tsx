import { screen, waitFor } from "@testing-library/react";
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
});

describe("ProfileRoute — minimal, per plan §3", () => {
  it("shows the teacher name and a sign-out affordance", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderProfile();
    await waitFor(() => expect(screen.getByText("Ms Perera")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("invents nothing beyond name and sign-out — no settings/preferences copy", async () => {
    vi.mocked(client.getHome).mockResolvedValue(HOME_SUMMARY);
    renderProfile();
    await waitFor(() => expect(screen.getByText("Ms Perera")).toBeInTheDocument());
    expect(screen.queryByText(/settings/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/preferences/i)).not.toBeInTheDocument();
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
