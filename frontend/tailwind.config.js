/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    // Mobile-first, per plan §8: base 375-639 (no prefix), 640-1023 (sm), >=1024 (lg).
    // Tailwind's defaults already land on these breakpoints, declared explicitly so they
    // cannot silently drift if the preset changes upstream.
    screens: {
      sm: "640px",
      lg: "1024px",
    },
    extend: {
      colors: {
        // Semantic tokens for the three watch states (see lib/presentation.ts WatchStatus).
        // Colour is only ever a SECONDARY cue — every consumer must also render an icon and
        // text (plan §9). Never reference these as the sole signal of state.
        watch: {
          watching: {
            bg: "#FEF2F2",
            border: "#FCA5A5",
            fg: "#991B1B",
            icon: "#DC2626",
          },
          noConcern: {
            bg: "#F0FDF4",
            border: "#86EFAC",
            fg: "#166534",
            icon: "#16A34A",
          },
          gettingStarted: {
            bg: "#F8FAFC",
            border: "#CBD5E1",
            fg: "#475569",
            icon: "#64748B",
          },
        },
      },
    },
  },
  plugins: [],
}
