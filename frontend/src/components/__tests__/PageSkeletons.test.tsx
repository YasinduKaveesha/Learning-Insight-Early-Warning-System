import { render, screen } from "@testing-library/react";
import type { ComponentType } from "react";
import { describe, expect, it } from "vitest";
import {
  ClassroomSkeleton,
  HomeSkeleton,
  JoinRequestsSkeleton,
  ProfileSkeleton,
  ReportsSkeleton,
  StudentDetailSkeleton,
  StudentSessionsSkeleton,
  WatchListSkeleton,
} from "../skeletons/PageSkeletons";

const PAGES: [string, ComponentType, string][] = [
  ["Home", HomeSkeleton, "Loading your dashboard"],
  ["Class", ClassroomSkeleton, "Loading class"],
  ["Student", StudentDetailSkeleton, "Loading student"],
  ["Sessions", StudentSessionsSkeleton, "Loading sessions"],
  ["Watch list", WatchListSkeleton, "Loading watch list"],
  ["Join requests", JoinRequestsSkeleton, "Loading join requests"],
  ["Reports", ReportsSkeleton, "Loading reports"],
  ["Profile", ProfileSkeleton, "Loading profile"],
];

describe.each(PAGES)("%s skeleton", (_name, Skeleton, label) => {
  it("is announced once, as loading, by name", () => {
    render(<Skeleton />);
    const regions = screen.getAllByRole("status");
    expect(regions).toHaveLength(1);
    expect(regions[0]).toHaveAccessibleName(label);
    expect(regions[0]).toHaveAttribute("aria-busy", "true");
  });

  it("shows no text and no numbers -- nothing a teacher could read as data", () => {
    const { container } = render(<Skeleton />);
    expect(container.textContent?.trim()).toBe("");
  });

  it("hides every shape from screen readers, so they hear one announcement, not forty", () => {
    const { container } = render(<Skeleton />);
    const bones = container.querySelectorAll("[data-skeleton-bone]");
    expect(bones.length).toBeGreaterThan(0);
    bones.forEach((bone) => expect(bone).toHaveAttribute("aria-hidden", "true"));
  });

  it("only pulses for people who have not asked their device to reduce motion", () => {
    const { container } = render(<Skeleton />);
    container.querySelectorAll("[data-skeleton-bone]").forEach((bone) => {
      expect(bone.className).toMatch(/motion-safe:animate-pulse/);
      expect(bone.className).not.toMatch(/(^|\s)animate-pulse/);
    });
  });
});
