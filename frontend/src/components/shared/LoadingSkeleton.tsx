export interface LoadingSkeletonProps {
  /** Number of skeleton rows/cards matching the final layout — never a bare
   * spinner over an empty page (plan §8). */
  rows?: number;
  /** Height of one skeleton block in pixels, so a card skeleton and a stat
   * tile skeleton can share this component. */
  rowHeight?: number;
}

export function LoadingSkeleton({ rows = 3, rowHeight = 72 }: LoadingSkeletonProps) {
  return (
    <div role="status" aria-label="Loading" className="flex flex-col gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          style={{ height: rowHeight }}
          className="animate-pulse rounded-lg bg-slate-200"
        />
      ))}
    </div>
  );
}
