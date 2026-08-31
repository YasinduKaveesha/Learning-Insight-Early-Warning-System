import {
  skillBarPositionFromBounds,
  skillDirectionLabel,
  type SkillProgress as SkillProgressModel,
} from "../../lib/presentation";

export interface SkillProgressRowProps {
  skill: SkillProgressModel;
  bounds: { min: number; max: number };
  /** UI-refinement pass: which of the 6 categorical bar colours this row
   * uses (cycles — a 7th skill repeats the 1st colour). Purely a visual
   * distinguisher between rows, not a status signal — direction (the word
   * beside the name) and bar length still carry the actual information. */
  colorIndex: number;
}

const SKILL_BAR_COLOR_CLASSES = [
  "bg-skillBar-1",
  "bg-skillBar-2",
  "bg-skillBar-3",
  "bg-skillBar-4",
  "bg-skillBar-5",
];

/**
 * One skill's direction and relative bar position — deliberately NOT its
 * practice count (integration_docs/04 §5: mastery is uncalibrated and not
 * skill-differentiated — identical BKT parameters across all seven skills,
 * TEST_FIXTURE_ONLY — and `practiceCount` has no real source at all, see
 * api/types.ts). No threshold, no "Mastered" badge, no percentage, no number
 * label anywhere in this component.
 *
 * A null bar position renders NO bar, with "not enough data" — never a flat
 * line, because in a system whose entire target is flatness, rendering
 * unknown as flat manufactures the exact signal being predicted (plan §4.4).
 */
export function SkillProgressRow({ skill, bounds, colorIndex }: SkillProgressRowProps) {
  const position = skillBarPositionFromBounds(skill.relativeLevel, bounds);
  const barColorClass = SKILL_BAR_COLOR_CLASSES[colorIndex % SKILL_BAR_COLOR_CLASSES.length];
  return (
    <div className="flex flex-col gap-1 py-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[15px] font-bold text-ink-primary">{skill.displayName}</span>
        {/* UI-refinement pass: when there's no position, the "Not enough
            data" line below already says so — showing "not enough data"
            here too was a redundant duplicate. Still shown for a real
            direction (improving/not moving). */}
        {position !== null ? (
          <span className="text-sm text-ink-secondary">{skillDirectionLabel(skill.direction)}</span>
        ) : null}
      </div>
      {position === null ? (
        <p className="text-sm text-ink-secondary">Not enough data</p>
      ) : (
        <div className="h-5 w-full rounded-full bg-surface2">
          <div className={`h-5 rounded-full ${barColorClass}`} style={{ width: `${position}%` }} />
        </div>
      )}
    </div>
  );
}

export interface SkillProgressListProps {
  skills: SkillProgressModel[];
  bounds: Record<string, { min: number; max: number }>;
}

export function SkillProgressList({ skills, bounds }: SkillProgressListProps) {
  return (
    <div className="flex flex-col">
      {skills.map((skill, i) => (
        <SkillProgressRow
          key={skill.skillId}
          skill={skill}
          bounds={bounds[skill.skillId] ?? { min: -0.5, max: 0.5 }}
          colorIndex={i}
        />
      ))}
    </div>
  );
}
