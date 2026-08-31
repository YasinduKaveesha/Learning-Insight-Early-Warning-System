import { useId, useState } from "react";
import { recommendationLabel, type RecommendationDisplay } from "../../lib/presentation";

export interface RecommendationCardProps {
  recommendation: RecommendationDisplay;
  onAccept: (recommendationId: string) => void;
  onDismiss: (recommendationId: string) => void;
  onModify: (recommendationId: string, modifiedTo: string) => void;
}

/**
 * PRESENTATIONAL ONLY — calls its callbacks and performs no persistence of
 * its own. Kind is rendered through recommendationLabel()'s lookup, which
 * has a readable fallback, so an unknown kind can never crash this card.
 *
 * No "Accept all" control exists anywhere in this file or its callers —
 * batch-approving suggestions about individual children defeats the point
 * of requiring a human decision (docs/12 §6).
 */
export function RecommendationCard({
  recommendation,
  onAccept,
  onDismiss,
  onModify,
}: RecommendationCardProps) {
  const [isModifying, setIsModifying] = useState(false);
  const [modifiedText, setModifiedText] = useState("");
  const modifyFieldId = useId();

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-900">
          {recommendationLabel(recommendation.kind)} — {recommendation.targetSkillDisplayName}
        </span>
      </div>

      {/* Evidence shown WITH the action, never behind a tap (docs/12 §6). */}
      <p className="text-sm text-slate-700">
        <span className="font-medium">Why: </span>
        {recommendation.evidenceSummary}
      </p>

      <p className="text-xs text-slate-500">
        {recommendation.status === "pending" ? "Not yet applied" : statusLabel(recommendation)}
        {" · "}
        Expires after session {recommendation.expiresAfterSession}
      </p>

      {isModifying ? (
        <div className="flex flex-col gap-2">
          <label htmlFor={modifyFieldId} className="text-xs font-medium text-slate-700">
            What should this be changed to?
          </label>
          <textarea
            id={modifyFieldId}
            value={modifiedText}
            onChange={(e) => setModifiedText(e.target.value)}
            className="min-h-[44px] rounded-lg border border-slate-300 p-2 text-sm"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                onModify(recommendation.recommendationId, modifiedText);
                setIsModifying(false);
              }}
              disabled={modifiedText.trim().length === 0}
              className="min-h-[44px] flex-1 rounded-lg bg-slate-900 px-3 text-sm font-medium text-white disabled:opacity-40"
            >
              Save change
            </button>
            <button
              type="button"
              onClick={() => setIsModifying(false)}
              className="min-h-[44px] rounded-lg border border-slate-300 px-3 text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        // Accept / Modify / Dismiss: equally weighted, NEVER adjacent — and
        // at 375px "never adjacent" means visually, not just in DOM order
        // (Step 4 review ruling A). A mis-tap here decides something about a
        // child, so each control gets real vertical distance and a distinct
        // visual weight, not just a 4px spacer: Accept is a full-width solid
        // block, Modify is a full-width outline block one gap below it, and
        // Dismiss sits below a rule with extra top margin, deliberately the
        // furthest thumb-travel from Accept. None of the three uses colour
        // to signal "less/more correct" — the weight difference is about
        // making the tap targets unmistakably separate finger-hits, not
        // about ranking the choices.
        <div className="flex flex-col gap-3 pt-1">
          <button
            type="button"
            onClick={() => onAccept(recommendation.recommendationId)}
            className="min-h-[44px] w-full rounded-lg bg-slate-900 px-3 text-sm font-semibold text-white"
          >
            Accept
          </button>
          <button
            type="button"
            onClick={() => setIsModifying(true)}
            className="min-h-[44px] w-full rounded-lg border-2 border-slate-400 px-3 text-sm font-semibold text-slate-800"
          >
            Modify
          </button>
          <div className="mt-2 border-t border-slate-200 pt-3">
            <button
              type="button"
              onClick={() => onDismiss(recommendation.recommendationId)}
              className="min-h-[44px] w-full rounded-lg px-3 text-sm font-medium text-slate-600 underline underline-offset-2"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function statusLabel(recommendation: RecommendationDisplay): string {
  switch (recommendation.status) {
    case "accepted":
      return "Accepted";
    case "dismissed":
      return "Dismissed";
    case "modified":
      return recommendation.modifiedActionSummary
        ? `Modified: ${recommendation.modifiedActionSummary}`
        : "Modified";
    default:
      return "Not yet applied";
  }
}
