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
