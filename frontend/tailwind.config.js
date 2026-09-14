/** @type {import('tailwindcss').Config} */
//
// Step 8: the MathMingo design tokens, ported from Upadya/Dev/frontend/src
// /theme/theme.ts (READ ONLY — values hand-copied, nothing imported; that
// app is React Native/Expo). This file IS the semantic layer components
// use via utility classes — no component may hard-code a hex value.
//
// Kept in sync with src/theme/tokens.ts (the same hex values, for the few
// consumers — recharts' stroke/fill props — that need a literal string
// rather than a class name). theme/__tests__/tokensSync.test.ts parses both
// files and asserts they match, so the two act as one source despite being
// physically two files.
//
// See src/theme/tokens.ts's header comment for the three deliberate
// deviations from a literal port (textMuted banned from text, watch-status
// colours reassigned away from red, successSoft/successText derived) and
// the full contrast-ratio measurements in the Step 8 report.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    // Mobile-first, per plan §8: base 375-639 (no prefix), 640-1023 (sm), >=1024 (lg).
    // PLAN §8 WINS ON LAYOUT — the theme's own layout.contentMaxWidth (640)
    // is a single-column mobile-game value; this dashboard needs ~1200px at
    // >=1024 with a persistent left nav (see AppNav.tsx), which is what the
    // "lg" breakpoint and each screen's max-w wrapper already implement.
    // Colour and type come from the theme; widths, breakpoints and
    // navigation come from the plan.
    screens: {
      sm: "640px",
      lg: "1024px",
    },
    extend: {
      colors: {
        // The page behind the cards. Light grey, so a white `surface1` card
        // reads as a card rather than as the page itself.
        //
        // History, because this value has moved twice: it was a light grey,
        // then white at explicit direction (the UI-refinement pass, when it
        // became flush with surface1), and is grey again at explicit direction
        // on 2026-09-14. `foreground` (#2f3136) on it measures 11.4:1, and
        // `ink-secondary` clears AA, so nothing that reads well on white stops
        // reading well here.
        background: "#f2f3f5",
        foreground: "#2f3136",
        surface1: "#ffffff",
        surface2: "#eaebee",
        surface3: "#dcdfe4",

        primary: {
          DEFAULT: "#ff6b68",
          hover: "#f05653",
          soft: "#ffe5e4",
          // 2.78:1 on `primary` — fails AA text contrast. Do not use as
          // text/icon colour on a primary fill; use `foreground` (4.68:1).
          foreground: "#ffffff",
        },
        secondary: {
          DEFAULT: "#b3e0fc",
          soft: "#eaf5fe",
          foreground: "#1a4360",
        },
        accent: {
          yellow: "#f2cd38",
          green: "#7bd3aa",
          blue: "#3ca6f8",
          red: "#f0504d",
        },
        success: {
          DEFAULT: "#7bd3aa",
          // Derived — not in the source palette. See tokens.ts header.
          soft: "#eaf9f1",
          text: "#1e5e42",
        },
        warning: "#f2cd38",
        danger: {
          DEFAULT: "#f0504d",
          soft: "#fde8e8",
          // 3.52:1 on `danger` — fails AA text contrast (passes only the
          // large-text 3:1 threshold). Prefer `foreground` text on
          // `danger.soft` for anything readable.
          foreground: "#ffffff",
          // Derived — not in the source palette. 5.56:1 on `surface1`, for
          // inline form-validation error TEXT only (e.g. CreateClassDialog's
          // duplicate-name message) — never for a watch status.
          text: "#c62b28",
        },

        ink: {
          primary: "#2f3136",
          secondary: "#686d76",
          // FAILS WCAG AA (~2.6:1). Never use for meaningful text — see
          // tokens.ts header and the Step 8 report's contrast table.
          muted: "#9398a1",
          disabled: "#c1c5cc",
        },

        border: {
          DEFAULT: "#e2e4e8",
          strong: "#cdcfd5",
        },
        // DASHBOARD-LOCAL OVERRIDE (hardening pass): darkened from the
        // source palette's #3ca6f8 (same as accent.blue) to clear WCAG
        // 1.4.11's 3:1 non-text threshold — measures 3.36:1 against
        // `background` and 3.69:1 against `surface1`. Step 8 flagged this
        // rather than substituting a colour on its own judgment; this pass
        // is the authorised fix. See tokens.ts header for the full
        // rationale and ratios.
        "focus-ring": "#2589dc",

        // Watch status — reassigned away from red (docs/12 §7: never
        // alarming; "Worth watching right now" is an invitation to look,
        // not a warning). Colour is always secondary to icon + text.
        watch: {
          watching: {
            bg: "#eaf5fe", // secondary.soft
            border: "#b3e0fc", // secondary
            fg: "#1a4360", // secondary.foreground
          },
          noConcern: {
            bg: "#eaf9f1", // success.soft
            border: "#7bd3aa", // success
            fg: "#1e5e42", // success.text
          },
          gettingStarted: {
            bg: "#ffffff", // surface1
            border: "#cdcfd5", // border.strong
            fg: "#686d76", // ink.secondary
          },
        },

        // UI-refinement pass: a third soft-tint colour for Home's stat
        // tiles (Getting Started), alongside watch.watching (blue) and
        // watch.noConcern (green) reused for the other two. New tint, not
        // a re-port — foreground (#2f3136) on this bg measures 11.72:1,
        // clearing AA with margin.
        statAmber: {
          bg: "#fdf3d0",
          border: "#f2cd38", // accentYellow
          fg: "#2f3136", // foreground
        },

        // UI-refinement pass: 5-colour categorical palette for skill-
        // progress bars, exact values given — one hue per row, cycling
        // (rows 6-7 repeat rows 2-3's colours). coral/blue/green reuse
        // primary/accentBlue/accentGreen; amber and purple are new.
        // FLAGGED, not substituted: measured against `surface2` (the bar
        // track) these are ~1.5-2.3:1, under WCAG 1.4.11's 3:1 for a
        // meaningful non-text graphic (purple, ~3.35:1, is the exception).
        // Not overridden without asking, per this app's established
        // pattern for a flagged-but-given colour.
        skillBar: {
          1: "#ff6b68", // coral = primary
          2: "#3ca6f8", // blue = accentBlue
          3: "#7bd3aa", // green = accentGreen
          4: "#ffb51f", // amber
          5: "#9a64df", // purple
        },

        // UI-refinement pass: soft-purple card tint for Suggestions —
        // same bg/border/fg shape as watch.watching / watch.noConcern /
        // statAmber, built from the skillBar purple hue so the palette
        // stays internally consistent. foreground on this bg measures
        // 10.93:1, clearing AA with margin.
        suggestionPurple: {
          bg: "#f0e8fb",
          border: "#9a64df", // same hue as skillBar.5
          fg: "#2f3136", // foreground
          // Accept: solid dark purple, white text — 7.38:1. Dismiss: a
          // slightly deeper purple tint than the card's own bg (so it
          // still reads as its own surface), foreground text — 9.27:1.
          accept: "#6b3fa0",
          dismissBg: "#e4d3f7",
        },
      },

      fontFamily: {
        // Self-hosted via @fontsource/nunito (imported in main.tsx) rather
        // than a Google Fonts runtime request. Real fallback stack, not
        // just "sans-serif".
        sans: [
          "Nunito",
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      fontSize: {
        // xs/sm/base/lg overridden to the ported line-heights; subtitle and
        // title are new keys. `title` (40/46) is in the scale for parity
        // but deliberately UNUSED on any dense mobile screen in this app —
        // see the Step 8 report's "diverged from a literal port" section.
        xs: ["12px", { lineHeight: "16px" }],
        sm: ["14px", { lineHeight: "21px" }],
        base: ["16px", { lineHeight: "24px" }],
        lg: ["18px", { lineHeight: "27px" }],
        subtitle: ["24px", { lineHeight: "31px" }],
        title: ["40px", { lineHeight: "46px" }],
      },
      letterSpacing: {
        label: "0.7px",
        button: "0.4px",
      },

      borderRadius: {
        // Extends (not replaces) Tailwind's scale — rounded-2xl/3xl/full
        // keep their defaults; sm/md/lg/xl now resolve to the brand scale,
        // so every existing `rounded-lg` etc. picks this up automatically.
        sm: "8px",
        md: "12px",
        lg: "20px",
        xl: "28px",
      },
      boxShadow: {
        elevated: "0 4px 16px rgba(0, 0, 0, 0.1)",
      },
      transitionDuration: {
        fast: "80ms",
        normal: "200ms",
        slow: "350ms",
      },
    },
  },
  plugins: [],
}
