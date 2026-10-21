/**
 * THE CANONICAL TOKEN SOURCE (Step 8) — ported from the MathMingo design
 * system at Upadya/Dev/frontend/src/theme/theme.ts (READ ONLY, a different
 * project — values were read and hand-copied, nothing is imported from
 * there; that app is React Native/Expo and its tokens are JS numbers, not
 * CSS).
 *
 * This file and tailwind.config.js's `theme.extend` MUST stay in sync —
 * tailwind.config.js is what components use via utility classes
 * (bg-primary, text-ink-secondary, ...); this file exists only because a
 * few consumers (recharts' `stroke`/`fill` props) need an actual hex
 * string, not a class name, and there is no build-time bridge between a
 * plain-JS Tailwind config and typed application code in this project's
 * toolchain. `theme/__tests__/tokensSync.test.ts` parses both files and
 * asserts every value here matches tailwind.config.js — that automated
 * check is what makes these two files behave as ONE semantic layer despite
 * being physically two. Never hand a raw hex to a component from anywhere
 * else; import from here (for JS) or use the Tailwind classes (for JSX).
 *
 * ============================================================================
 * THREE DELIBERATE DEVIATIONS FROM A LITERAL PORT (see the Step 8 report for
 * the full contrast-ratio table):
 *
 * 1. `textMuted` (#9398a1) measures ~2.6:1 against `background` (originally
 *    a light grey; the UI-refinement pass that changed `background` to
 *    white made this measure worse still) — fails WCAG AA's 4.5:1 for text
 *    either way. It is kept here for parity with the source palette but
 *    MUST NOT be used for any meaningful text; `textSecondary` (~4.7:1,
 *    ~5.2:1 on white) replaces it everywhere prose needs a secondary tone.
 * 2. The watch-status colours (`watchWatching`, `watchNoConcern`,
 *    `watchGettingStarted`) are NOT in the source palette at all — they are
 *    assembled from non-red brand families (secondary/blue, success/green,
 *    neutral) specifically BECAUSE `danger`/`accentRed` must never be a
 *    watch-status colour (docs/12 §7: "Worth watching right now" is an
 *    invitation to look, not an alarm — a red badge on a child is the exact
 *    failure the tone rule exists to prevent).
 * 3. `successSoft` and `successText` do not exist in the source palette
 *    (which has no light-tint or text-safe variant of `success`/
 *    `accentGreen` — `accentGreen` itself is only ~1.8:1 on white, unusable
 *    as text or an icon glyph). `successSoft` follows the same "soft tint"
 *    pattern as the source's own `primarySoft`/`secondarySoft`/`dangerSoft`;
 *    `successText` is a darkened green measured at ≥7:1 on both `surface1`
 *    and `successSoft`.
 * 4. `dangerText` is likewise not in the source palette. `danger`
 *    (#f0504d) measures only 3.52:1 on white — fails AA for normal text —
 *    yet an inline form validation error (CreateClassDialog's duplicate
 *    name message) conventionally needs red TEXT, not just a soft-fill
 *    chip. `dangerText` is a darkened red measured at 5.56:1 on
 *    `surface1`, used ONLY for that kind of inline error text — never for
 *    a watch status or anything describing a child.
 * 5. `focusRing` (hardening-pass fix, was flagged not fixed in Step 8): the
 *    literal MathMingo value (#3ca6f8, same as `accentBlue`) measures only
 *    ~2.4:1 against `background` and ~2.6:1 against `surface1` — Step 8
 *    explicitly declined to override an unnamed token on its own judgment
 *    and flagged it instead. Now authorised and fixed: darkened to
 *    #2589dc, which measures 3.36:1 / 3.69:1 against the same two
 *    backgrounds — clears WCAG 1.4.11's 3:1 non-text threshold against
 *    BOTH with margin, while staying recognisably the same blue hue. This
 *    is a DASHBOARD-LOCAL override, not a re-port — `accentBlue` elsewhere
 *    in this file keeps the original literal value; only the focus
 *    indicator, which plan §9 requires to be visible and AA, is darkened.
 * ============================================================================
 */

export const colors = {
  // --- Ported directly from theme.ts ---------------------------------------
  // The page behind the cards. Grey -> white (UI-refinement pass) -> grey again
  // at explicit direction, 2026-09-14: a white card needs a page that is not
  // also white. See deviation note 1 above, which measured `textMuted` against
  // the ORIGINAL grey -- that measurement applies again now.
  background: "#f2f3f5",
  foreground: "#2f3136",
  surface1: "#ffffff",
  surface2: "#eaebee",
  surface3: "#dcdfe4",

  primary: "#ff6b68",
  primaryHover: "#f05653",
  primarySoft: "#ffe5e4",
  // primaryForeground (#ffffff) measures only 2.78:1 against `primary` —
  // fails AA even for large text. Never pair white text on a `primary`
  // background for anything readable; use `foreground` (4.68:1) instead.
  // The literal value is kept here only for parity with the source token
  // name, not because it's safe to use as text.
  primaryForeground: "#ffffff",

  secondary: "#b3e0fc",
  secondarySoft: "#eaf5fe",
  secondaryForeground: "#1a4360",

  accentYellow: "#f2cd38",
  accentGreen: "#7bd3aa",
  accentBlue: "#3ca6f8",
  accentRed: "#f0504d",

  success: "#7bd3aa",
  warning: "#f2cd38",
  danger: "#f0504d",
  dangerSoft: "#fde8e8",
  // Same caveat as primaryForeground: dangerForeground/danger measures
  // 3.52:1, which fails AA for normal text (passes only the 3:1 large-text
  // threshold). Prefer `foreground` text on `dangerSoft` for anything
  // readable; reserve solid `danger` fills for non-text UI (borders, small
  // icons) where the 3:1 non-text-contrast threshold applies instead.
  dangerForeground: "#ffffff",

  textPrimary: "#2f3136",
  textSecondary: "#686d76",
  // FAILS WCAG AA (~2.6:1 on background, ~2.9:1 on surface1). Do not use
  // for any meaningful text — see the file header. Kept only for parity
  // with the source token name and for genuinely decorative use.
  textMuted: "#9398a1",
  textDisabled: "#c1c5cc",

  border: "#e2e4e8",
  borderStrong: "#cdcfd5",
  // DASHBOARD-LOCAL OVERRIDE (deviation 5 below) — darkened from the
  // source palette's #3ca6f8 to clear WCAG 1.4.11's 3:1 non-text
  // threshold. See the file header for the measured ratios and rationale.
  focusRing: "#2589dc",

  // --- Derived, NOT in the source palette (deviations 3 & 4 above) ---------
  successSoft: "#eaf9f1",
  successText: "#1e5e42",
  dangerText: "#c62b28",

  // --- Watch status (deviation 2 above) — NEVER danger/accentRed -----------
  watchWatchingBg: "#eaf5fe", // = secondarySoft
  watchWatchingBorder: "#b3e0fc", // = secondary
  watchWatchingFg: "#1a4360", // = secondaryForeground
  watchNoConcernBg: "#eaf9f1", // = successSoft
  watchNoConcernBorder: "#7bd3aa", // = success
  watchNoConcernFg: "#1e5e42", // = successText
  watchGettingStartedBg: "#ffffff", // = surface1
  watchGettingStartedBorder: "#cdcfd5", // = borderStrong
  watchGettingStartedFg: "#686d76", // = textSecondary

  // UI-refinement pass: third soft-tint colour for Home's stat tiles
  // (statAmber in tailwind.config.js — kept in sync here). New tint;
  // `foreground` on this bg measures 11.72:1, clearing AA with margin.
  statAmberBg: "#fdf3d0",

  // Solid card fills (toneCard in tailwind.config.js — kept in sync here).
  // A middle set from Upadya's blue/green/orange. FAILS AA for white text
  // (3.35 / 3.40 / 2.67:1) — flagged, not substituted; text on these is
  // kept bold.
  toneCardBlueBg: "#3c8df0",
  toneCardBlueBorder: "#2f7fdd",
  toneCardGreenBg: "#1f9e6e",
  toneCardGreenBorder: "#188a5f",
  toneCardAmberBg: "#e8862a",
  toneCardAmberBorder: "#d07420",

  // UI-refinement pass: 5-colour categorical skill-bar palette (skillBar
  // in tailwind.config.js — kept in sync here). Exact values given;
  // contrast against `surface2` flagged, not overridden — see that
  // file's comment for the full rationale.
  skillBar1: "#ff6b68",
  skillBar2: "#3ca6f8",
  skillBar3: "#7bd3aa",
  skillBar4: "#ffb51f",
  skillBar5: "#9a64df",

  // UI-refinement pass: soft-purple card tint for Suggestions
  // (suggestionPurple in tailwind.config.js — kept in sync here).
  suggestionPurpleBg: "#f0e8fb",
  suggestionPurpleAccept: "#6b3fa0",
  suggestionPurpleDismissBg: "#e4d3f7",
} as const;

export const chart = {
  // recharts <Line stroke> values — the only place raw hex legitimately
  // reaches a component (SVG props take colour strings, not class names).
  line: colors.foreground,
  lineMuted: colors.textSecondary,
} as const;

// radius and motion durations are NOT re-exported as JS constants here
// (hardening pass: an earlier version had them, unused by any component) —
// they're consumed entirely through Tailwind's borderRadius/
// transitionDuration extensions in tailwind.config.js, which is the only
// place anything needs a class name from. Unlike `colors`, no component
// needs a literal radius/duration string in a JS prop (recharts is the
// only such consumer, and it needs colours, not spacing).

export type ThemeColors = typeof colors;
