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
 * 1. `textMuted` (#9398a1) measures ~2.6:1 against #f4f4f6 — fails WCAG AA's
 *    4.5:1 for text. It is kept here for parity with the source palette but
 *    MUST NOT be used for any meaningful text; `textSecondary` (~4.7:1)
 *    replaces it everywhere prose needs a secondary tone.
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
 * ============================================================================
 */

export const colors = {
  // --- Ported directly from theme.ts ---------------------------------------
  background: "#f4f4f6",
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
  // Ported as-is. MEASURED AND FLAGGED (see Step 8 report): as a 2px focus
  // outline against `background`/`surface1`, this measures ~2.4–2.6:1,
  // below WCAG 1.4.11's 3:1 non-text-contrast threshold for focus
  // indicators. The source design system does not provide an alternative,
  // and the instruction set for this port did not authorise substituting
  // one (unlike textMuted and the watch-status colours, which it named
  // explicitly). Browsers' own default focus outline and this app's
  // focus-visible ring-offset (see tailwind.config.js) add a further
  // contrast edge in practice, but the ring colour ALONE does not clear
  // 3:1 — flagged rather than silently patched.
  focusRing: "#3ca6f8",

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
} as const;

export const chart = {
  // recharts <Line stroke> values — the only place raw hex legitimately
  // reaches a component (SVG props take colour strings, not class names).
  line: colors.foreground,
  lineMuted: colors.textSecondary,
} as const;

export const radius = { sm: "8px", md: "12px", lg: "20px", xl: "28px" } as const;

export const motion = { fast: "80ms", normal: "200ms", slow: "350ms" } as const;

export type ThemeColors = typeof colors;
