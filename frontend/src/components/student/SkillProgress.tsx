import {
  skillBarPositionFromBounds,
  skillDirectionLabel,
  type SkillProgress as SkillProgressModel,
} from "../../lib/presentation";

export interface SkillProgressRowProps {
  skill: SkillProgressModel;
  bounds: { min: number; max: number };
}

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
export function SkillProgressRow({ skill, bounds }: SkillProgressRowProps) {
  const position = skillBarPositionFromBounds(skill.relativeLevel, bounds);
  return (
    <div className="flex flex-col gap-1 py-1.5">
      <div className="flex items-center justify-between">
        <span className="text-sm text-ink-primary">{skill.displayName}</span>
        <span className="text-xs text-ink-secondary">{skillDirectionLabel(skill.direction)}</span>
      </div>
      {position === null ? (
        <p className="text-xs text-ink-secondary">Not enough data</p>
      ) : (
        <div className="h-2 w-full rounded-full bg-surface2">
          <div className="h-2 rounded-full bg-foreground" style={{ width: `${position}%` }} />
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
    <div className="flex flex-col divide-y divide-border">
      {skills.map((skill) => (
        <SkillProgressRow
          key={skill.skillId}
          skill={skill}
          bounds={bounds[skill.skillId] ?? { min: -0.5, max: 0.5 }}
        />
      ))}
    </div>
  );
}
