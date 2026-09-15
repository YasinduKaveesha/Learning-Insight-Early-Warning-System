# Dashboard frontend

The teacher's screens for the Learning Insight & Early Warning System. React 18 + TypeScript +
Vite, TanStack Query for data, Tailwind for styling, Vitest for tests. Phone-first: every
screen is designed at 375px and widens from there.

See the [repository README](../README.md) for how the pieces fit together, and
`../../plan/frontend_plan.md` for the full build plan.

## Run it

```bash
npm install
npm run dev          # http://localhost:5173
```

| Command | What it does |
|---|---|
| `npm run dev` | Development server with hot reload |
| `npm test` | Vitest suite (341 tests) |
| `npm run typecheck` | TypeScript, no build output |
| `npm run lint` | Oxlint |
| `npm run build` | Production build into `dist/` |

## Configuration

Copy `.env.example` to `.env.local`:

| Variable | Meaning |
|---|---|
| `VITE_API_BASE_URL` | Dashboard backend, e.g. `http://localhost:8100` |
| `VITE_STUDENT_APP_BASE_URL` | Student app API, e.g. `http://localhost:8000` |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | The student app's Supabase project, for sign-in |
| `VITE_USE_MOCK` | `true` runs entirely on built-in fixtures, no backend needed |

**Changing `tailwind.config.js` needs a dev-server restart**; Vite does not pick it up on its
own, and the change silently appears to do nothing.

## How it is put together

```
src/api/         The seam: one ApiClient interface, three implementations
src/routes/      One folder per screen
src/components/  Shared UI, grouped by the thing it shows (class, student, shared)
src/lib/         presentation.ts — the display rules, and where most logic tests live
src/auth/        Supabase session, sign-in and sign-up, route guard
src/theme/       Colour tokens, with contrast tests
```

**Two backends, on purpose.** `httpClient.ts` reads from the dashboard backend.
`studentAppClient.ts` writes classes, join-request decisions and class deletions straight to
the student app, because the dashboard is read-only toward that data. `client.ts` picks the
real client or `MockClient` (fixtures) and is the only file that knows which.

**Display rules live in `lib/presentation.ts`**, not in components: what counts as "worth
watching", the order of a class list, what a handled suggestion does to a count, the wording
of every status. They are pure functions with tests, so a screen cannot quietly disagree with
another screen.

## Rules the tests enforce

Some tests exist to protect promises rather than behaviour, and will fail on wording changes
that look harmless:

- **Vocabulary.** No screen may say diagnose, detect, screen, disorder, deficit, disability,
  impairment, or name a research group. Learners are *flagged for teacher review*.
- **No invented numbers.** A teacher-facing figure must come from the API. Where there is no
  real value, the screen says so ("Not practised yet", "Not enough history yet") rather than
  showing a zero or an empty chart.
- **Never colour alone.** A status always carries an icon and words too.
- **Tap targets are at least 44px**, and destructive actions are never next to safe ones.
- **Layering.** Components may not import `api/types.ts` directly; they take what a route
  gives them.
