import { useState } from "react";
import { ClassCard } from "../../components/class/ClassCard";
import { ClassInfoDialog } from "../../components/class/ClassInfoDialog";
import { ClassKeyDialog } from "../../components/class/ClassKeyDialog";
import { CreateClassDialog } from "../../components/class/CreateClassDialog";
import { Chart } from "../../components/shared/Chart";
import { DisclosureFooter } from "../../components/shared/DisclosureFooter";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorState } from "../../components/shared/ErrorState";
import { FramingLine } from "../../components/shared/FramingLine";
import { LoadingSkeleton } from "../../components/shared/LoadingSkeleton";
import { SearchField } from "../../components/shared/SearchField";
import { SectionHeader } from "../../components/shared/SectionHeader";
import { StatTile } from "../../components/shared/StatTile";
import { GettingStartedNotice } from "../../components/status/GettingStartedNotice";
import { PriorityBadge } from "../../components/status/PriorityBadge";
import { TrajectoryChip } from "../../components/status/TrajectoryChip";
import { WatchStatusBadge } from "../../components/status/WatchStatusBadge";
import { ExplanationBlock } from "../../components/student/ExplanationBlock";
import { RecommendationCard } from "../../components/student/RecommendationCard";
import { SessionCard } from "../../components/student/SessionCard";
import { SkillProgressList } from "../../components/student/SkillProgress";
import { StudentCard } from "../../components/student/StudentCard";
import type {
  LearnerSnapshot,
  RecommendationDisplay,
  SessionEntry,
  SkillProgress as SkillProgressModel,
} from "../../lib/presentation";

// --- Sample display data, one row per state that must be demonstrated -----

const WATCHING_SNAPSHOT: LearnerSnapshot = {
  studentId: "sample-1",
  displayName: "Amara",
  classId: "class-3blue",
  sessionNumber: 7,
  watchFlag: true,
  rankWithinSnapshot: 1,
  evidenceStatus: "sufficient_evidence",
  sessionsCompleted: 7,
  practiceTrajectory: { source: "practice_accuracy", state: "needs_attention" },
  explanation:
    "Subtraction has not improved across the last four sessions despite regular practice, and hints are rarely being used.",
  lastActiveDate: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
  accuracySparkline: [0.6, 0.55, 0.5, 0.48, 0.45],
  engagementSparkline: [0.7, 0.68, 0.65, 0.66, 0.64],
  modelVersion: "target_a_logreg_armA_v1",
  inferenceTimestamp: new Date().toISOString(),
};

const NO_CONCERN_SNAPSHOT: LearnerSnapshot = {
  ...WATCHING_SNAPSHOT,
  studentId: "sample-2",
  displayName: "Kavya",
  watchFlag: false,
  rankWithinSnapshot: null,
  practiceTrajectory: { source: "practice_accuracy", state: "stable" },
  explanation: null,
};

const GETTING_STARTED_SNAPSHOT: LearnerSnapshot = {
  ...WATCHING_SNAPSHOT,
  studentId: "sample-3",
  displayName: "Nimal",
  watchFlag: false,
  rankWithinSnapshot: null,
  evidenceStatus: "insufficient_exposure",
  sessionsCompleted: 1,
  practiceTrajectory: { source: "practice_accuracy", state: "unknown" },
  explanation: null,
  accuracySparkline: [],
  engagementSparkline: [],
};

const IMPROVING_BUT_FLAGGED_SNAPSHOT: LearnerSnapshot = {
  ...WATCHING_SNAPSHOT,
  studentId: "sample-4",
  displayName: "Kavindu",
  practiceTrajectory: { source: "practice_accuracy", state: "improving" },
  explanation:
    "Game engagement has been declining across recent sessions, and skill mastery has slowed across recent sessions.",
};

const SAMPLE_SKILLS: SkillProgressModel[] = [
  { skillId: "counting", displayName: "Counting", direction: "improving", relativeLevel: 0.18, practiceCount: 4 },
  { skillId: "number_sense", displayName: "Number sense", direction: "not_moving", relativeLevel: -0.06, practiceCount: 5 },
  { skillId: "place_value", displayName: "Place value", direction: "unknown", relativeLevel: null, practiceCount: 1 },
];
const SAMPLE_BOUNDS = { counting: { min: -0.3, max: 0.3 }, number_sense: { min: -0.3, max: 0.3 }, place_value: { min: -0.3, max: 0.3 } };

const NORMAL_SESSION: SessionEntry = {
  sessionNumber: 5,
  date: new Date().toISOString(),
  practice: { present: true, accuracy: 0.82, pace: "typical", hintsUsed: 3 },
  games: {
    present: true,
    dataComplete: true,
    state: "on_target",
    stateReason: null,
    engagementDriver: "steady completion",
    frustrationDriver: null,
  },
};

const NO_GAMES_SESSION: SessionEntry = {
  ...NORMAL_SESSION,
  sessionNumber: 6,
  games: {
    present: false,
    dataComplete: true,
    state: null,
    stateReason: null,
    engagementDriver: null,
    frustrationDriver: null,
  },
};

const INCOMPLETE_TELEMETRY_SESSION: SessionEntry = {
  ...NORMAL_SESSION,
  sessionNumber: 7,
  games: {
    present: true,
    dataComplete: false,
    state: null,
    stateReason: "telemetry_gap",
    engagementDriver: null,
    frustrationDriver: null,
  },
};

const PENDING_RECOMMENDATION: RecommendationDisplay = {
  recommendationId: "rec-1",
  kind: "review",
  targetSkillDisplayName: "Place value",
  evidenceSummary:
    "Subtraction has been practised for four sessions without improvement, and place value is still developing.",
  status: "pending",
  modifiedActionSummary: null,
  expiresAfterSession: 14,
};

const UNKNOWN_KIND_RECOMMENDATION: RecommendationDisplay = {
  ...PENDING_RECOMMENDATION,
  recommendationId: "rec-2",
  kind: "some_future_kind_not_yet_seen",
};

const ACCEPTED_RECOMMENDATION: RecommendationDisplay = {
  ...PENDING_RECOMMENDATION,
  recommendationId: "rec-3",
  status: "accepted",
};

function noop() {
  // Gallery callbacks are inert — this surface only demonstrates rendering.
}

function GallerySection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3 border-b border-slate-200 pb-6">
      <h2 className="text-sm font-bold uppercase tracking-wide text-slate-400">{title}</h2>
      {children}
    </section>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-xs text-slate-400">{label}</p>
      {children}
    </div>
  );
}

/**
 * Dev-only component gallery — every component in every state at 375px.
 * This route is excluded from production in App.tsx (import.meta.env.DEV).
 */
export default function GalleryRoute() {
  const [dialogOpen, setDialogOpen] = useState<"key" | "info" | "create" | null>(null);
  const [search, setSearch] = useState("");

  return (
    <div className="mx-auto flex max-w-[375px] flex-col gap-6 p-4">
      <h1 className="text-lg font-bold">Component Gallery</h1>

      <GallerySection title="FramingLine / DisclosureFooter">
        <FramingLine />
        <DisclosureFooter disclosure="Literature-informed synthetic data — not clinical evidence." />
      </GallerySection>

      <GallerySection title="WatchStatusBadge — three states">
        <Row label="watching">
          <WatchStatusBadge status={{ kind: "watching", label: "Worth watching right now", priority: 1 }} />
        </Row>
        <Row label="no_concern">
          <WatchStatusBadge status={{ kind: "no_concern", label: "No current concern identified" }} />
        </Row>
        <Row label="getting_started">
          <WatchStatusBadge
            status={{ kind: "getting_started", label: "Getting Started", sessionsCompleted: 1, sessionsRequired: 3 }}
          />
        </Row>
      </GallerySection>

      <GallerySection title="PriorityBadge">
        <PriorityBadge priority={4} />
      </GallerySection>

      <GallerySection title="TrajectoryChip — practice accuracy only (D17)">
        <Row label="improving"><TrajectoryChip trajectory={{ source: "practice_accuracy", state: "improving" }} /></Row>
        <Row label="stable"><TrajectoryChip trajectory={{ source: "practice_accuracy", state: "stable" }} /></Row>
        <Row label="needs_attention"><TrajectoryChip trajectory={{ source: "practice_accuracy", state: "needs_attention" }} /></Row>
        <Row label="unknown (not enough data)"><TrajectoryChip trajectory={{ source: "practice_accuracy", state: "unknown" }} /></Row>
      </GallerySection>

      <GallerySection title="GettingStartedNotice">
        <GettingStartedNotice sessionsCompleted={1} />
      </GallerySection>

      <GallerySection title="StudentCard — watching / no_concern / getting_started / two-signal">
        <StudentCard snapshot={WATCHING_SNAPSHOT} onClick={noop} />
        <StudentCard snapshot={NO_CONCERN_SNAPSHOT} onClick={noop} />
        <StudentCard snapshot={GETTING_STARTED_SNAPSHOT} onClick={noop} />
        <Row label="improving on practice accuracy but still flagged (two-signal path)">
          <StudentCard snapshot={IMPROVING_BUT_FLAGGED_SNAPSHOT} onClick={noop} />
        </Row>
      </GallerySection>

      <GallerySection title="SkillProgress — direction + bar, no count, null bar">
        <SkillProgressList skills={SAMPLE_SKILLS} bounds={SAMPLE_BOUNDS} />
      </GallerySection>

      <GallerySection title="ExplanationBlock">
        <Row label="present"><ExplanationBlock explanation={WATCHING_SNAPSHOT.explanation} /></Row>
        <Row label="null (renders nothing below this line)"><ExplanationBlock explanation={null} /></Row>
      </GallerySection>

      <GallerySection title="Chart — practice + engagement series">
        <Chart title="Practice accuracy" values={WATCHING_SNAPSHOT.accuracySparkline} trendSentence="Accuracy has declined across the last five sessions." />
        <Chart title="Game engagement" values={WATCHING_SNAPSHOT.engagementSparkline} trendSentence="Engagement has been broadly steady across recent sessions." />
      </GallerySection>

      <GallerySection title="RecommendationCard — pending / unknown kind / accepted">
        <RecommendationCard recommendation={PENDING_RECOMMENDATION} onAccept={noop} onDismiss={noop} onModify={noop} />
        <RecommendationCard recommendation={UNKNOWN_KIND_RECOMMENDATION} onAccept={noop} onDismiss={noop} onModify={noop} />
        <RecommendationCard recommendation={ACCEPTED_RECOMMENDATION} onAccept={noop} onDismiss={noop} onModify={noop} />
      </GallerySection>

      <GallerySection title="SessionCard — normal / no games / incomplete telemetry">
        <SessionCard session={NORMAL_SESSION} />
        <SessionCard session={NO_GAMES_SESSION} />
        <SessionCard session={INCOMPLETE_TELEMETRY_SESSION} />
      </GallerySection>

      <GallerySection title="ClassCard">
        <ClassCard name="Grade 3 Blue" grade="GRADE_3" studentCount={9} toWatchCount={3} pendingRequestCount={2} onClick={noop} />
      </GallerySection>

      <GallerySection title="Dialogs">
        <button type="button" onClick={() => setDialogOpen("key")} className="min-h-[44px] rounded-lg border border-slate-300 px-3 text-sm">
          Open ClassKeyDialog
        </button>
        <button type="button" onClick={() => setDialogOpen("info")} className="min-h-[44px] rounded-lg border border-slate-300 px-3 text-sm">
          Open ClassInfoDialog
        </button>
        <button type="button" onClick={() => setDialogOpen("create")} className="min-h-[44px] rounded-lg border border-slate-300 px-3 text-sm">
          Open CreateClassDialog
        </button>
        <ClassKeyDialog isOpen={dialogOpen === "key"} onClose={() => setDialogOpen(null)} className="Grade 3 Blue" classKey="7K4P92" />
        <ClassInfoDialog isOpen={dialogOpen === "info"} onClose={() => setDialogOpen(null)} className="Grade 3 Blue" grade="GRADE_3" classKey="7K4P92" studentCount={9} />
        <CreateClassDialog isOpen={dialogOpen === "create"} onClose={() => setDialogOpen(null)} onSubmit={noop} nameError="A class named 'Grade 3 Blue' already exists." />
      </GallerySection>

      <GallerySection title="StatTile / SectionHeader / SearchField">
        <div className="grid grid-cols-3 gap-2">
          <StatTile label="Students" value={83} />
          <StatTile label="To Watch" value={7} caption="of 83 students" />
          <StatTile label="Getting Started" value={9} infoText="These students are still building their learning history." />
        </div>
        <SectionHeader title="Students to Watch" subtitle="Based on recent learning activity" />
        <SearchField label="Search students" value={search} onChange={setSearch} resultCount={0} />
      </GallerySection>

      <GallerySection title="Four states — Loading / Empty / Error / Getting Started">
        <Row label="Loading"><LoadingSkeleton rows={2} /></Row>
        <Row label="Empty"><EmptyState message="No students yet. Share the key 7K4P92." /></Row>
        <Row label="Error"><ErrorState message="Couldn't load this class. Check your connection and try again." onRetry={noop} /></Row>
        <Row label="Getting Started (first-class, not empty)"><GettingStartedNotice sessionsCompleted={2} /></Row>
      </GallerySection>
    </div>
  );
}
