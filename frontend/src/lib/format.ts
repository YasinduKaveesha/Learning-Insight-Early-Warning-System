// Dates, relative time, and counts. Deliberately no percentage-confidence
// formatter and no model-version formatter — those values never reach the UI.

export function formatDate(isoDate: string): string {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return isoDate;
  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
}

/** "Today" / "Yesterday" / "N days ago" / "N weeks ago", relative to now. */
export function formatRelativeDate(isoDate: string, now: Date = new Date()): string {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return isoDate;

  const dayMs = 24 * 60 * 60 * 1000;
  const diffDays = Math.floor((now.getTime() - date.getTime()) / dayMs);

  if (diffDays <= 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays} days ago`;

  const diffWeeks = Math.floor(diffDays / 7);
  if (diffWeeks === 1) return "1 week ago";
  if (diffWeeks < 5) return `${diffWeeks} weeks ago`;

  return formatDate(isoDate);
}

/** "7 of 83 students" — the count and its total, never the count alone (plan §1). */
export function formatCountOfTotal(count: number, total: number, noun: string): string {
  return `${count} of ${total} ${noun}`;
}

/**
 * A chart's required text alternative (plan §8: "every chart is accompanied
 * by a sentence describing the trend; that sentence IS the alternative, not
 * decoration"). Purely descriptive of the shape of the series — no number,
 * no percentage, no threshold language, and deliberately NOT the withheld
 * three-tier engagement classification (D17): this describes what a line
 * chart looks like, it does not re-introduce Improving/Stable/Needs
 * Attention for engagement.
 */
export function describeTrend(label: string, values: number[]): string {
  if (values.length < 2) return `Not enough data yet to show a trend for ${label.toLowerCase()}.`;
  const first = values[0]!;
  const last = values[values.length - 1]!;
  const delta = last - first;
  const threshold = 0.03;
  if (delta > threshold) return `${label} has risen across the last ${values.length} sessions.`;
  if (delta < -threshold) return `${label} has fallen across the last ${values.length} sessions.`;
  return `${label} has stayed broadly steady across the last ${values.length} sessions.`;
}
