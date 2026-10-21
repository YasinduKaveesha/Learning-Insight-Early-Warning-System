import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { compd, type CompdProfile, type CompdStudentProfiles } from "../../../api/compdClient";
import CompdStudentRoute from "../CompdStudentRoute";

function renderStudent(path = "/compd/students/s-hiran") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/compd/students/:studentId" element={<CompdStudentRoute />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function profile(overrides: Partial<CompdProfile>): CompdProfile {
  return {
    session_id: "run",
    memory_level: "high",
    attention_level: "medium",
    number_sense_level: "low",
    processing_speed_level: "Fast",
    recommendation: "Practise number bonds to 10 with objects first.",
    features: { accuracy: 0.8, avg_response_time_ms: 3200, retry_rate: 0.1, hint_rate: 0.2, total_questions: 10 },
    generated_at: "2026-10-20T09:30:00Z",
    ...overrides,
  };
}

const NEWER = profile({ session_id: "run-newer", generated_at: "2026-10-20T09:30:00Z" });
const OLDER = profile({
  session_id: "run-older",
  memory_level: "low",
  processing_speed_level: "Slow",
  features: { accuracy: 0.5, avg_response_time_ms: 6000, retry_rate: 0.3, hint_rate: 0.4, total_questions: 8 },
  generated_at: "2026-10-18T14:05:00Z",
});

const PROFILES: CompdStudentProfiles = {
  student_id: "s-hiran",
  name: "Hiran",
  classroom_name: "Grade 3 Blue",
  items: [NEWER, OLDER],
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Student page — Profile (U4)", () => {
  it("shows compD's teacher view: header, four dimension cards, recommendation and stats", async () => {
    vi.spyOn(compd, "getStudentProfiles").mockResolvedValue(PROFILES);
    renderStudent();

    expect(await screen.findByRole("heading", { level: 1, name: "Hiran" })).toBeInTheDocument();
    expect(screen.getByText("Grade 3 Blue")).toBeInTheDocument();
    expect(screen.getByText("Based on 10 questions · 80% correctness")).toBeInTheDocument();

    const cards = within(screen.getByRole("region", { name: "Cognitive Skill Profile" }));
    for (const [title, word, blurb] of [
      ["Memory Performance", "Strong", "How well you hold numbers and steps in mind."],
      ["Attention Level", "Developing", "How focused you stay while solving."],
      ["Number Sense", "Needs practice", "Your feel for how numbers work."],
      ["Processing Speed", "Quick", "How quickly you answer confidently."],
    ] as const) {
      const card = cards.getByRole("heading", { name: title }).closest("li")!;
      expect(within(card).getByText(word)).toBeInTheDocument();
      expect(within(card).getByText(blurb)).toBeInTheDocument();
    }
    expect(cards.getByText("Suggested focus")).toBeInTheDocument();
    expect(cards.getByText("Practise number bonds to 10 with objects first.")).toBeInTheDocument();
    for (const [label, value] of [["Avg time", "3.2s"], ["Retry rate", "10%"], ["Hint rate", "20%"], ["Interactions", "10"]] as const) {
      expect(cards.getByText(label).nextElementSibling).toHaveTextContent(value);
    }
  });

  it("never shows a confidence value, the model version, brain power or a disclosure", async () => {
    vi.spyOn(compd, "getStudentProfiles").mockResolvedValue(PROFILES);
    const { container } = renderStudent();
    await screen.findByText("Based on 10 questions · 80% correctness");
    const text = container.textContent ?? "";
    for (const banned of [/confidence/i, /model/i, /rule-based/i, /brain/i, /personal best/i, /synthetic data/i]) {
      expect(text).not.toMatch(banned);
    }
  });

  it("a child with no runs gets the empty state", async () => {
    vi.spyOn(compd, "getStudentProfiles").mockResolvedValue({ ...PROFILES, items: [] });
    renderStudent();
    expect(await screen.findByText("This student hasn't done a Thinking Skills activity yet.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Profile History" })).not.toBeInTheDocument();
  });
});

describe("Student page — History (U5)", () => {
  it("lists each profile newest first with date, chips, correctness and questions, then the legend", async () => {
    vi.spyOn(compd, "getStudentProfiles").mockResolvedValue(PROFILES);
    renderStudent();
    const history = within(await screen.findByRole("region", { name: "Profile History" }));

    expect(history.getByText("2 profiles recorded")).toBeInTheDocument();
    const cards = history.getAllByRole("listitem").filter((li) => li.parentElement?.tagName === "OL");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]!).getByText("Correctness 80% · Questions 10")).toBeInTheDocument();
    expect(within(cards[1]!).getByText("Correctness 50% · Questions 8")).toBeInTheDocument();
    expect(within(cards[1]!).getByText("Takes time")).toBeInTheDocument();
    for (const label of ["Memory", "Attention", "Number Sense", "Speed"]) {
      expect(within(cards[0]!).getByText(label)).toBeInTheDocument();
    }
    // The date and time are on each card (formatted in the browser's locale).
    expect(within(cards[0]!).getByText(/–/)).toBeInTheDocument();

    expect(history.getByRole("heading", { name: "What the levels mean" })).toBeInTheDocument();
    expect(history.getByText("Strong / Quick")).toBeInTheDocument();
    expect(history.getByText("Developing / Steady")).toBeInTheDocument();
    expect(history.getByText("Needs practice / Takes time")).toBeInTheDocument();
    // compD never rendered trend bars or expanding rows; neither does this.
    expect(history.queryByRole("button")).not.toBeInTheDocument();
  });

  it("with #history, the History section is scrolled into view once the data has loaded", async () => {
    const scrolled: Element[] = [];
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (this: Element) {
      scrolled.push(this);
    };
    try {
      vi.spyOn(compd, "getStudentProfiles").mockResolvedValue(PROFILES);
      renderStudent("/compd/students/s-hiran#history");
      await screen.findByRole("region", { name: "Profile History" });
      await waitFor(() => expect(scrolled.map((el) => el.id)).toEqual(["history"]));
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it("without #history, nothing scrolls", async () => {
    const scrollIntoView = vi.fn();
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;
    try {
      vi.spyOn(compd, "getStudentProfiles").mockResolvedValue(PROFILES);
      renderStudent();
      await screen.findByRole("region", { name: "Profile History" });
      expect(scrollIntoView).not.toHaveBeenCalled();
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it("asks for one page of 20 profiles for this child, and its back link returns to the Students tab", async () => {
    const call = vi.spyOn(compd, "getStudentProfiles").mockResolvedValue(PROFILES);
    renderStudent();
    await screen.findByText("2 profiles recorded");
    expect(call).toHaveBeenCalledWith("s-hiran", 20);
    expect(screen.getByRole("link", { name: "Back to Thinking Skills" })).toHaveAttribute("href", "/compd?tab=students");
  });
});
