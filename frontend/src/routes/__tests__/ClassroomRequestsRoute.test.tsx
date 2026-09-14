import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ClassroomRequestsRoute from "../classroom-requests/ClassroomRequestsRoute";
import { renderRoute } from "./testUtils";

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return {
    DuplicateClassNameError: actual.DuplicateClassNameError,
    isDuplicateClassNameError: actual.isDuplicateClassNameError,
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
    },
  };
});

const { client } = await import("../../api/client");

const COHORT = {
  classId: "class-1",
  className: "Grade 3 Blue",
  grade: "GRADE_3" as const,
  classKey: "7K4P92",
  studentCount: 8,
  toWatchCount: 2,
  gettingStartedCount: 1,
  pendingRequestCount: 2,
  students: [],
  disclosure: "Literature-informed synthetic data — not clinical evidence.",
};

const REQUESTS = [
  { requestId: "req-1", studentDisplayName: "Devni", requestedDate: "2026-08-29T09:00:00.000Z" },
  { requestId: "req-2", studentDisplayName: "Sithumi", requestedDate: "2026-08-30T09:00:00.000Z" },
];

function renderRequests() {
  return renderRoute(<ClassroomRequestsRoute />, {
    path: "/classes/:classId/requests",
    initialPath: "/classes/class-1/requests",
  });
}

beforeEach(() => {
  vi.mocked(client.getCohort).mockReset();
  vi.mocked(client.getJoinRequests).mockReset();
  vi.mocked(client.approveJoinRequest).mockReset().mockResolvedValue(undefined);
  vi.mocked(client.rejectJoinRequest).mockReset().mockResolvedValue(undefined);
});

describe("ClassroomRequestsRoute — requests sit above the roster", () => {
  it("renders each request with name, requested date, Approve and Reject", async () => {
    vi.mocked(client.getCohort).mockResolvedValue(COHORT);
    vi.mocked(client.getJoinRequests).mockResolvedValue(REQUESTS);
    renderRequests();

    await waitFor(() => expect(screen.getByText("Devni")).toBeInTheDocument());
    expect(screen.getByText("Sithumi")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Approve" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Reject" })).toHaveLength(2);
  });

  it("Approve and Reject are not adjacent and are distinguished by label", async () => {
    vi.mocked(client.getCohort).mockResolvedValue(COHORT);
    vi.mocked(client.getJoinRequests).mockResolvedValue([REQUESTS[0]!]);
    renderRequests();

    await waitFor(() => expect(screen.getByText("Devni")).toBeInTheDocument());
    const approve = screen.getByRole("button", { name: "Approve" });
    const reject = screen.getByRole("button", { name: "Reject" });
    expect(approve.textContent).not.toBe(reject.textContent);
    expect(approve.className).not.toBe(reject.className);
    // Reject sits behind an explicit visual break, same ruling as
    // RecommendationCard's Accept/Modify/Dismiss (Step 5 review ruling A).
    expect(reject.parentElement!.className).toMatch(/border-t/);
  });

  it("clicking Approve calls the client and removes the request from the list", async () => {
    vi.mocked(client.getCohort).mockResolvedValue(COHORT);
    vi.mocked(client.getJoinRequests).mockResolvedValue(REQUESTS);
    renderRequests();

    await waitFor(() => expect(screen.getByText("Devni")).toBeInTheDocument());
    await userEvent.click(screen.getAllByRole("button", { name: "Approve" })[0]!);
    expect(client.approveJoinRequest).toHaveBeenCalledWith("class-1", "req-1");
  });

  it("clicking Reject calls the client with the request id", async () => {
    vi.mocked(client.getCohort).mockResolvedValue(COHORT);
    vi.mocked(client.getJoinRequests).mockResolvedValue(REQUESTS);
    renderRequests();

    await waitFor(() => expect(screen.getByText("Sithumi")).toBeInTheDocument());
    const rejectButtons = screen.getAllByRole("button", { name: "Reject" });
    await userEvent.click(rejectButtons[1]!);
    expect(client.rejectJoinRequest).toHaveBeenCalledWith("class-1", "req-2");
  });
});

describe("ClassroomRequestsRoute — four states", () => {
  it("loading renders skeletons, not a spinner", () => {
    vi.mocked(client.getCohort).mockReturnValue(new Promise(() => {}));
    vi.mocked(client.getJoinRequests).mockReturnValue(new Promise(() => {}));
    renderRequests();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("empty state shows the class key so the teacher can re-share it", async () => {
    vi.mocked(client.getCohort).mockResolvedValue({ ...COHORT, pendingRequestCount: 0 });
    vi.mocked(client.getJoinRequests).mockResolvedValue([]);
    renderRequests();
    await waitFor(() =>
      expect(
        screen.getByText("No requests pending right now. Share the class key so students can join."),
      ).toBeInTheDocument(),
    );
  });

  it("error state says what failed and offers retry, never a raw error string", async () => {
    vi.mocked(client.getCohort).mockResolvedValue(COHORT);
    vi.mocked(client.getJoinRequests).mockRejectedValue(new Error("500 Internal Server Error"));
    renderRequests();
    await waitFor(() =>
      expect(screen.getByText(/Couldn't load join requests/)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/500/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("ClassroomRequestsRoute — framing, disclosure, forbidden vocabulary", () => {
  it("shows neither the framing line nor the disclosure footer (removed at explicit direction, 2026-09-14)", async () => {
    vi.mocked(client.getCohort).mockResolvedValue(COHORT);
    vi.mocked(client.getJoinRequests).mockResolvedValue(REQUESTS);
    renderRequests();
    await waitFor(() => expect(screen.getAllByRole("button", { name: /approve/i }).length).toBeGreaterThan(0));
    expect(screen.queryByText("The system flags learners for teacher review.")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Literature-informed synthetic data — not clinical evidence."),
    ).not.toBeInTheDocument();
  });

  const FORBIDDEN = [
    "diagnos",
    "dyscalculia",
    "disorder",
    "deficit",
    "disability",
    "impairment",
    "screening",
    "detected",
    "population",
    "dd_subtype",
    "confidence",
  ];

  it("renders no banned vocabulary or probability/score in the loaded state", async () => {
    vi.mocked(client.getCohort).mockResolvedValue(COHORT);
    vi.mocked(client.getJoinRequests).mockResolvedValue(REQUESTS);
    const { container } = renderRequests();
    await waitFor(() => expect(screen.getByText("Devni")).toBeInTheDocument());
    const text = container.textContent!.toLowerCase();
    for (const term of FORBIDDEN) expect(text).not.toContain(term);
  });

  it("renders no banned vocabulary in the empty state", async () => {
    vi.mocked(client.getCohort).mockResolvedValue({ ...COHORT, pendingRequestCount: 0 });
    vi.mocked(client.getJoinRequests).mockResolvedValue([]);
    const { container } = renderRequests();
    await waitFor(() => expect(screen.getByText(/Share the class key/)).toBeInTheDocument());
    const text = container.textContent!.toLowerCase();
    for (const term of FORBIDDEN) expect(text).not.toContain(term);
  });
});
