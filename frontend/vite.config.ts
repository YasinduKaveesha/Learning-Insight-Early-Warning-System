/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/testSetup.ts'],
    // Hardening-pass fix (defect B): the default 'forks' pool spawns a
    // fresh child process AND a fresh jsdom environment per test file
    // (28 files) — the cumulative environment-setup cost is exactly what a
    // full run's ~790s of "environment" time was. Worse, under that many
    // concurrent forks contending for CPU, @testing-library/user-event's
    // real-timer-based interactions (type/click delays) can genuinely
    // exceed a test's timeout even though the test itself is correct —
    // that's what produced the one-off "Modify captures..." timeout,
    // reproducible only under full-suite load, never in isolation.
    // 'threads' keeps the same per-file isolation (fresh module registry
    // per file, so the several tests here that exercise the REAL
    // MockClient's mutable fixture state — classManagement.test.ts,
    // classReports.test.ts, sessionReachability.test.ts — still can't leak
    // state into each other) but reuses worker threads instead of spawning
    // OS processes, which is what actually removes the setup cost. Capping
    // threads below the machine's full core count leaves headroom so
    // real-timer interactions aren't starved by sibling test files
    // fighting for the same cores. See the hardening-pass report for three
    // consecutive full-suite runs proving this fixed the flake, not just a
    // raised timeout.
    pool: 'threads',
    maxWorkers: 4,
  },
})
