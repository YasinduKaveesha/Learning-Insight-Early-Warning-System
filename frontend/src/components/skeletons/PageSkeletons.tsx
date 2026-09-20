import type { ReactNode } from "react";
import { Bone, SkeletonRegion } from "./Skeleton";

/**
 * One skeleton per page, each shaped like that page's real layout (2026-09-16). Class names
 * mirror the real components' sizes -- `min-h-[88px]` like `ClassCard`, `min-h-[96px]` like
 * `StatTile`, `min-h-[220px]` like a watch-list card -- so the page does not shift when the data
 * arrives. If a real component changes size, change its skeleton here too.
 *
 * Pinned headers (back and Home buttons, tabs) are NOT drawn here: every page already renders
 * those immediately, loading or not, so the teacher can always leave a page that is still loading.
 */

/** Rounded card outline -- the shared frame most skeletons sit in. */
function CardFrame({ className = "", children }: { className?: string; children?: ReactNode }) {
  return (
    <div className={`rounded-lg border border-border bg-surface1 p-3 ${className}`}>{children}</div>
  );
}

// ---------------------------------------------------------------------------------------------
// Home
// ---------------------------------------------------------------------------------------------

export function HomeSkeleton() {
  return (
    <SkeletonRegion label="Loading your dashboard" className="flex flex-col gap-4">
      {/* The watch card: title, big number, "View watch list" pill. */}
      <div className="flex flex-col gap-4 rounded-2xl border border-border bg-surface1 px-5 py-10">
        <Bone className="h-5 w-40" />
        <Bone className="ml-10 h-16 w-24" />
        <Bone className="h-9 w-36 self-end rounded-full" />
      </div>

      {/* The three stat tiles. */}
      <div className="grid grid-cols-3 gap-2">
        {Array.from({ length: 3 }, (_, i) => (
          <CardFrame key={i} className="flex min-h-[96px] flex-col justify-between">
            <Bone className="h-4 w-16" />
            <Bone className="h-7 w-10 self-end" />
          </CardFrame>
        ))}
      </div>

      {/* "Your Classes" and the class cards. */}
      <Bone className="mx-1 h-5 w-28" />
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <CardFrame key={i} className="flex min-h-[88px] flex-col justify-between">
            <Bone className="h-4 w-14" />
            <Bone className="h-7 w-24 self-end" />
          </CardFrame>
        ))}
      </div>
    </SkeletonRegion>
  );
}

// ---------------------------------------------------------------------------------------------
// Class page
// ---------------------------------------------------------------------------------------------

/** A student card: name, "last active" line, and the status word at the right. */
function StudentCardBone() {
  return (
    <CardFrame className="relative flex min-h-[76px] flex-col justify-center gap-2">
      <Bone className="h-5 w-32" />
      <Bone className="h-4 w-24" />
      <Bone className="absolute right-3 top-1/2 h-6 w-20 -translate-y-1/2" />
    </CardFrame>
  );
}

export function ClassroomSkeleton() {
  return (
    <SkeletonRegion label="Loading class" className="flex flex-col gap-4">
      {/* Search box. */}
      <Bone className="h-11 w-full rounded-full" />

      {/* Students / To Watch / Getting Started tiles. */}
      <div className="grid grid-cols-3 gap-2">
        {Array.from({ length: 3 }, (_, i) => (
          <CardFrame key={i} className="flex min-h-[96px] flex-col justify-between">
            <Bone className="h-4 w-16" />
            <Bone className="h-7 w-10 self-end" />
          </CardFrame>
        ))}
      </div>

      {/* "Students to Watch" and its cards. */}
      <Bone className="mx-1 h-5 w-36" />
      <div className="flex flex-col gap-2">
        {Array.from({ length: 4 }, (_, i) => (
          <StudentCardBone key={i} />
        ))}
      </div>
    </SkeletonRegion>
  );
}

/** The class name pill in the class page header, while the class loads. */
export function ClassNamePillBone() {
  return <Bone className="h-8 w-20 rounded-full" />;
}

// ---------------------------------------------------------------------------------------------
// Student page
// ---------------------------------------------------------------------------------------------

export function StudentDetailSkeleton() {
  return (
    <SkeletonRegion label="Loading student" className="flex flex-col gap-4">
      {/* Status card. */}
      <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface1 p-4">
        <Bone className="h-4 w-48" />
      </div>

      {/* Skill progress: a label and a bar per skill. */}
      <section className="flex flex-col gap-2">
        <Bone className="mx-1 my-2 h-6 w-32" />
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="flex flex-col gap-1 py-1.5">
            <Bone className="h-4 w-28" />
            <Bone className="h-5 w-full rounded-full" />
          </div>
        ))}
      </section>

      {/* Suggestions: one suggestion card with its two buttons. */}
      <section className="flex flex-col gap-2">
        <Bone className="mx-1 my-2 h-6 w-28" />
        <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface1 p-4">
          <Bone className="h-5 w-40" />
          <Bone className="h-4 w-full" />
          <Bone className="h-4 w-3/4" />
          <Bone className="mt-1 h-11 w-full rounded-lg" />
          <Bone className="h-11 w-full rounded-lg" />
        </div>
      </section>
    </SkeletonRegion>
  );
}

/** The student's name in the student page header, while it loads. */
export function StudentNameBone() {
  return <Bone className="mx-auto h-6 w-32" />;
}

// ---------------------------------------------------------------------------------------------
// Student sessions
// ---------------------------------------------------------------------------------------------

export function StudentSessionsSkeleton() {
  return (
    <SkeletonRegion label="Loading sessions" className="flex flex-col gap-3">
      {Array.from({ length: 3 }, (_, i) => (
        <CardFrame key={i}>
          {/* "Session N" and the date. */}
          <div className="mb-2 flex items-center justify-between">
            <Bone className="h-4 w-20" />
            <Bone className="h-4 w-16" />
          </div>
          {/* Practice (B). */}
          <div className="flex flex-col gap-2 border-t border-border pt-2">
            <Bone className="h-4 w-24" />
            <Bone className="h-4 w-3/4" />
          </div>
          {/* Games (C). */}
          <div className="mt-2 flex flex-col gap-2 border-t border-border pt-2">
            <Bone className="h-4 w-20" />
            <Bone className="h-4 w-2/3" />
          </div>
        </CardFrame>
      ))}
    </SkeletonRegion>
  );
}

// ---------------------------------------------------------------------------------------------
// Watch list
// ---------------------------------------------------------------------------------------------

export function WatchListSkeleton() {
  return (
    <SkeletonRegion label="Loading watch list" className="flex flex-col gap-3">
      {Array.from({ length: 3 }, (_, i) => (
        <div
          key={i}
          className="flex min-h-[220px] flex-col gap-3 rounded-lg border border-border bg-surface1 p-4"
        >
          {/* Name, and the class pill at the right. */}
          <div className="flex items-start justify-between gap-2">
            <Bone className="h-5 w-32" />
            <Bone className="h-7 w-14 rounded-full" />
          </div>
          <Bone className="h-4 w-full" />
          <Bone className="h-4 w-5/6" />
          <Bone className="mt-auto h-10 w-full rounded-lg" />
        </div>
      ))}
    </SkeletonRegion>
  );
}

// ---------------------------------------------------------------------------------------------
// Join requests
// ---------------------------------------------------------------------------------------------

export function JoinRequestsSkeleton() {
  return (
    <SkeletonRegion label="Loading join requests" className="flex flex-col gap-3">
      {Array.from({ length: 2 }, (_, i) => (
        <CardFrame key={i} className="flex flex-col gap-2 p-4">
          {/* Name and "Requested <date>". */}
          <Bone className="h-4 w-32" />
          <Bone className="h-4 w-24" />
          {/* Approve, a divider, Reject. */}
          <div className="flex flex-col gap-3 pt-1">
            <Bone className="h-11 w-full rounded-full" />
            <div className="border-t border-border pt-3">
              <Bone className="h-11 w-full rounded-full" />
            </div>
          </div>
        </CardFrame>
      ))}
    </SkeletonRegion>
  );
}

// ---------------------------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------------------------

export function ReportsSkeleton() {
  return (
    <SkeletonRegion label="Loading reports" className="flex flex-col gap-4">
      {/* Three chart sections: a heading, the chart, its one-line summary. */}
      {Array.from({ length: 3 }, (_, i) => (
        <section key={i} className="flex flex-col gap-2">
          <Bone className="mx-1 my-2 h-5 w-44" />
          <CardFrame className="flex flex-col gap-2">
            <Bone className="h-4 w-40" />
            <Bone className="h-20 w-full sm:h-28 lg:h-32" />
            <Bone className="h-4 w-3/4" />
          </CardFrame>
        </section>
      ))}

      {/* Participation tiles. */}
      <section className="flex flex-col gap-2">
        <Bone className="mx-1 my-2 h-5 w-28" />
        <div className="grid grid-cols-3 gap-2">
          {Array.from({ length: 3 }, (_, i) => (
            <CardFrame key={i} className="flex min-h-[72px] flex-col justify-between">
              <Bone className="h-4 w-16" />
              <Bone className="h-6 w-8" />
            </CardFrame>
          ))}
        </div>
      </section>
    </SkeletonRegion>
  );
}

// ---------------------------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------------------------

export function ProfileSkeleton() {
  return (
    <SkeletonRegion label="Loading profile" className="flex flex-col gap-6">
      {/* Avatar and name. */}
      <div className="flex flex-col items-center gap-2">
        <Bone className="h-24 w-24 rounded-full" />
        <Bone className="h-6 w-40" />
      </div>

      {/* Name, email, grade, classes: an icon and two lines each. */}
      <div className="flex flex-col rounded-lg border border-border bg-surface1 p-3">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="flex items-center gap-3 py-2">
            <Bone className="h-10 w-10 shrink-0 rounded-full" />
            <div className="flex flex-1 flex-col gap-1.5">
              <Bone className="h-3 w-16" />
              <Bone className="h-4 w-40" />
            </div>
          </div>
        ))}
      </div>

      {/* Log out. */}
      <Bone className="h-11 w-full rounded-lg" />
    </SkeletonRegion>
  );
}
