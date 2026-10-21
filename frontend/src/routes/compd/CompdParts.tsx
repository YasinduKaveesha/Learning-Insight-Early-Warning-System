// Small pieces shared by the two CompD pages: the pinned header, a stat tile that
// takes text (compD's "Avg accuracy" is a percentage, which StatTile's number
// value cannot carry), and the level chip and bar.

import { ArrowLeft, House } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { CompdLevel, CompdSpeed } from "../../api/compdClient";
import {
  TONE_BAR_CLASSES,
  TONE_BAR_WIDTH,
  TONE_CHIP_CLASSES,
  levelTone,
  levelWord,
} from "../../lib/compdPresentation";

/** The same pinned header as the student page: back on the left, Home on the right. */
export function CompdHeader({
  title,
  backTo,
  backLabel,
  children,
}: {
  title: ReactNode;
  backTo: string;
  backLabel: string;
  children?: ReactNode;
}) {
  return (
    <div className="sticky top-0 z-20 -mx-4 -mt-4 flex flex-col gap-4 bg-background px-4 pb-2 pt-4">
      <header className="flex items-center justify-between gap-2">
        <Link
          to={backTo}
          aria-label={backLabel}
          className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-ink-primary"
        >
          <ArrowLeft aria-hidden="true" size={22} />
        </Link>
        <h1 className="flex-1 truncate text-center text-[18px] font-bold text-ink-primary">{title}</h1>
        <Link
          to="/"
          aria-label="Home"
          className="flex h-11 w-11 items-center justify-center rounded-full border border-border-strong text-ink-primary"
        >
          <House aria-hidden="true" size={22} />
        </Link>
      </header>
      {children}
    </div>
  );
}

const TILE_TONES = {
  blue: "border-toneCard-blue-border bg-toneCard-blue-bg",
  green: "border-toneCard-green-border bg-toneCard-green-bg",
  amber: "border-toneCard-amber-border bg-toneCard-amber-bg",
} as const;

/** compD's four summary tiles, in the dashboard's solid tile style. */
export function CompdTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: keyof typeof TILE_TONES;
}) {
  return (
    <div
      className={`flex min-h-[96px] flex-col justify-between gap-1 rounded-lg border p-3 text-white ${TILE_TONES[tone]}`}
    >
      <span className="text-sm font-bold">{label}</span>
      <span className="self-end text-2xl font-bold">{value}</span>
    </div>
  );
}

/** A level in the teacher's words (Q3), never colour alone. */
export function LevelChip({ level }: { level: CompdLevel | CompdSpeed }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-bold ${TONE_CHIP_CLASSES[levelTone(level)]}`}
    >
      {levelWord(level)}
    </span>
  );
}

/** compD's level bar. The word is beside it as text, so the bar only repeats it. */
export function LevelBar({ level }: { level: CompdLevel | CompdSpeed }) {
  const tone = levelTone(level);
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-surface2" aria-hidden="true">
      <div className={`h-full rounded-full ${TONE_BAR_CLASSES[tone]} ${TONE_BAR_WIDTH[tone]}`} />
    </div>
  );
}
