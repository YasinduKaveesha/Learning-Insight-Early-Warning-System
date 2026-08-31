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
        background: "#f4f4f6",
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
        // Ported as-is; measured below WCAG 1.4.11's 3:1 non-text threshold
        // as a bare outline colour — see tokens.ts header. Flagged in the
        // Step 8 report, not silently substituted.
        "focus-ring": "#3ca6f8",

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
