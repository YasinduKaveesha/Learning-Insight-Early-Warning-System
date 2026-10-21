import { Bone, SkeletonRegion } from "../../components/skeletons/Skeleton";

/**
 * The one skeleton of the CompD section (plan 03 §6), shaped like what it stands in
 * for, so the page does not jump when the data arrives. PageSkeletons.tsx is not
 * touched: the CompD pages keep their loading state beside them.
 *
 * - "tiles": the Students tab -- four tiles, then student cards.
 * - "list": the Questions tab and the AI drafts -- a column of cards.
 * - "profile": the student page -- the header card and four dimension cards.
 */
export function CompdPageSkeleton({
  variant,
  label,
}: {
  variant: "tiles" | "list" | "profile";
  label: string;
}) {
  return (
    <SkeletonRegion label={label} className="flex flex-col gap-3">
      {variant === "tiles" ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="flex min-h-[96px] flex-col justify-between rounded-lg border border-border bg-surface1 p-3">
              <Bone className="h-4 w-16" />
              <Bone className="h-7 w-10 self-end" />
            </div>
          ))}
        </div>
      ) : null}
      {variant === "profile" ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-surface1 p-4">
          <Bone className="h-5 w-48" />
          <Bone className="h-4 w-56" />
        </div>
      ) : null}
      {Array.from({ length: variant === "profile" ? 4 : 3 }, (_, i) => (
        <div key={i} className="flex min-h-[120px] flex-col gap-3 rounded-lg border border-border bg-surface1 p-3">
          <Bone className="h-5 w-40" />
          <Bone className="h-4 w-full" />
          <Bone className="h-4 w-2/3" />
        </div>
      ))}
    </SkeletonRegion>
  );
}
