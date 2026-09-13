import { useId, useState } from "react";
import { SUGGESTION_SOURCE_LABEL, type RecommendationDisplay } from "../../lib/presentation";

export interface RecommendationCardProps {
  recommendation: RecommendationDisplay;
  onAccept: (recommendationId: string) => void;
  onDismiss: (recommendationId: string) => void;
  onModify: (recommendationId: string, modifiedTo: string) => void;
}

/**
 * PRESENTATIONAL ONLY — calls its callbacks and performs no persistence of
 * its own. UI-refinement pass: the "{kind} — " prefix (via
 * recommendationLabel()) is dropped from the visible title; only the
 * target skill name renders now.
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
    <div className="flex flex-col gap-2 rounded-lg border border-suggestionPurple-border bg-suggestionPurple-bg p-4">
      <div className="flex items-center justify-between">
        {/* UI-refinement pass: dropped the "{kind} — " prefix (e.g.
            "Practice — ") — just the skill name now, matching the plain
            text style used elsewhere (e.g. skill progress rows). */}
        <span className="text-[17px] font-bold text-ink-primary">
          {recommendation.targetSkillDisplayName}
        </span>
      </div>

      {/* Evidence shown WITH the action, never behind a tap (docs/12 §6).
          UI-refinement pass: the "Why: " label is dropped — just the
          evidence text now. */}
      <p className="text-sm text-ink-primary">{recommendation.evidenceSummary}</p>
      <p className="text-[12px] text-ink-secondary">{SUGGESTION_SOURCE_LABEL}</p>

      {isModifying ? (
        <div className="flex flex-col gap-2">
          <label htmlFor={modifyFieldId} className="text-sm font-medium text-ink-primary">
            What should this be changed to?
          </label>
          <textarea
            id={modifyFieldId}
            value={modifiedText}
            onChange={(e) => setModifiedText(e.target.value)}
            className="min-h-[44px] rounded-lg border border-border-strong p-2 text-sm"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                onModify(recommendation.recommendationId, modifiedText);
                setIsModifying(false);
              }}
              disabled={modifiedText.trim().length === 0}
              className="min-h-[44px] flex-1 rounded-lg bg-primary px-3 text-sm font-bold text-foreground disabled:opacity-40"
            >
              Save change
            </button>
            <button
              type="button"
              onClick={() => setIsModifying(false)}
              className="min-h-[44px] rounded-lg border border-border-strong px-3 text-sm"
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
          {/* UI-refinement pass: solid dark purple matching the card's own
              theme (suggestionPurple.accept), white text — 7.38:1. */}
          <button
            type="button"
            onClick={() => onAccept(recommendation.recommendationId)}
            className="min-h-[44px] w-full rounded-lg bg-suggestionPurple-accept px-3 text-sm font-bold text-white"
          >
            Accept
          </button>
          <button
            type="button"
            onClick={() => setIsModifying(true)}
            className="min-h-[44px] w-full rounded-lg border-2 border-border-strong px-3 text-sm font-semibold text-ink-primary"
          >
            Modify
          </button>
          <div className="mt-2 border-t border-border pt-3">
            {/* UI-refinement pass: a deeper purple tint than the card's own
                background (suggestionPurple.dismissBg), foreground text —
                9.27:1 — replacing the previous danger-soft/pink pairing so
                Dismiss reads as part of this card's own colour family. */}
            <button
              type="button"
              onClick={() => onDismiss(recommendation.recommendationId)}
              className="min-h-[44px] w-full rounded-lg bg-suggestionPurple-dismissBg px-3 text-sm font-medium text-foreground underline underline-offset-2"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
