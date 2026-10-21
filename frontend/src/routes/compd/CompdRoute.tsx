import { useSearchParams } from "react-router-dom";
import { CompdHeader } from "./CompdParts";
import QuestionsTab from "./QuestionsTab";
import StudentsTab from "./StudentsTab";

type Tab = "students" | "questions";

/** compD's two teacher-home tiles, as two tabs (TeacherHomeScreen.tsx). The
 * welcome header and the tiles' one-line descriptions are dropped (plan 03 §5):
 * Home already greets the teacher, and the Questions line mentioned an AI key
 * that no longer exists. */
const TABS: readonly { value: Tab; label: string }[] = [
  { value: "students", label: "Students Dashboard" },
  { value: "questions", label: "Practice Questions" },
];

/**
 * /compd -- everything compD's teacher side had, opened from the CompD button on
 * Home (owner direction 2026-10-21; plan 01 §2a). The tab lives in `?tab=`, so Back and
 * a reload keep it; each tab loads its own data only when it is opened.
 */
export default function CompdRoute() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "questions" ? "questions" : "students";

  return (
    <div className="mx-auto flex max-w-[480px] lg:max-w-[1200px] flex-col gap-4 p-4 pb-8">
      <CompdHeader title="Thinking Skills" backTo="/" backLabel="Back to Home">
        {/* The tab markup of LoginRoute.tsx: real buttons in a tablist, so
            keyboard and screen readers get them for free. */}
        <div
          role="tablist"
          aria-label="Thinking Skills sections"
          className="grid grid-cols-2 gap-2 rounded-lg bg-primary-soft p-1"
        >
          {TABS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={tab === value}
              onClick={() => setParams({ tab: value })}
              className={`min-h-[44px] rounded-lg px-3 text-sm font-bold ${
                tab === value ? "bg-surface1 text-ink-primary shadow-sm" : "text-ink-secondary"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </CompdHeader>

      <div role="tabpanel" aria-label={tab === "students" ? "Students Dashboard" : "Practice Questions"}>
        {tab === "students" ? <StudentsTab /> : <QuestionsTab />}
      </div>
    </div>
  );
}
