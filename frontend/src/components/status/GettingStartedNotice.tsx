export interface GettingStartedNoticeProps {
  sessionsCompleted: number;
  sessionsRequired?: number;
  /** When given, personalises the notice for the Student Overview's
   * status-block replacement (plan §4.4): "<Name> is still building a
   * learning history — N of 3 sessions completed. ...". Omitted for the
   * compact cohort-card summary, which already shows the name beside it. */
  name?: string;
}

/**
 * "Getting Started", never "Insufficient Evidence" (docs/12 §3 — the
 * technical term sounds like a problem with the child). A first-class state,
 * never styled as a warning, never implying struggle — plain neutral card,
 * no warning colours or icons.
 */
export function GettingStartedNotice({
  sessionsCompleted,
  sessionsRequired = 3,
  name,
}: GettingStartedNoticeProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <p className="text-sm font-medium text-slate-800">Getting Started</p>
      <p className="mt-1 text-sm text-slate-600">
        {name
          ? `${name} is still building a learning history — ${sessionsCompleted} of ${sessionsRequired} sessions completed. More activity is needed before the system can identify a clear learning pattern.`
          : "This student is still building a learning history. More activity is needed before the system can identify a clear learning pattern."}
      </p>
      {!name ? (
        <p className="mt-2 text-xs text-slate-500">
          {sessionsCompleted} of {sessionsRequired} sessions
        </p>
      ) : null}
    </div>
  );
}
