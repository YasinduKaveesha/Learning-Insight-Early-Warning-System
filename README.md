# Learning Insight & Early Warning System

Component 3 of R26-IT-138: a teacher's dashboard for a primary-school mathematics app. It
reads what learners have done in that app and shows a teacher **which learners are worth a
closer look**, with the evidence that prompted it.

> **What this system does and does not claim.** It flags learners for teacher review. It does
> not diagnose, detect, identify or screen for anything, and nothing here is clinical
> evidence. Every screen is written to that rule, and tests enforce the vocabulary.

> **The learner telemetry in the demo is synthetic.** Identity, rosters, classes and join
> requests are real rows created by the student app's own API; the practice sessions behind
> the predictions are literature-informed synthetic data, because the live student app does
> not yet number sessions the way the model needs. Every API response carries a disclosure
> saying so.

## The three pieces

| Piece | Lives in | Port | Owns |
|---|---|---|---|
| **Dashboard frontend** | `frontend/` | 5173 | What a teacher sees |
| **Dashboard backend** | `backend/` | 8100 | Predictions, suggestions, class keys (`t3_*` tables) |
| **Student app backend** | `../../Upadya/Dev/backend` (separate repo, another team) | 8000 | Accounts, learners, classes, memberships, gameplay |

They are **separate backends** with separate images and separate compose projects. They share
one Postgres server, because this dashboard reads the student app's rosters — read-only. Every
write to a classroom or a membership (creating a class, approving a join request, deleting a
class) goes through the student app's own API, never through this backend.

Authentication is the student app's Supabase project: a teacher signs in there, and this
backend verifies that token against the project's public keys.

```
  browser ──▶ frontend (5173)
                 │
                 ├──▶ dashboard backend (8100) ──┐
                 │                               ├──▶ Postgres  (student app tables + t3_* tables)
                 └──▶ student app API (8000) ────┘
```

## Running the demo

Docker Desktop must be running. Full instructions live in each README; the short version:

```bash
# 1. student app: database + API
cd ../../Upadya/Dev/backend && docker compose up -d db api

# 2. dashboard backend
cd Learning-Insight-Early-Warning-System/backend && docker compose up -d --build

# 3. dashboard frontend
cd ../frontend && npm install && npm run dev
```

Then open <http://localhost:5173>. Both backends answer `GET /health/ready`.

Demo teacher: `yass@gmail.com` / `12345678`.

## What a teacher can do

- See how many learners are worth watching, per class and overall, with classes ordered by the
  share of the class flagged — and any class with a join request waiting first.
- Open a learner: their current status, the evidence behind it, skill progress, session history.
- Accept or change a suggested next step for a learner. Decisions are saved as research data
  and never change what the student app teaches.
- Create a class, share its key, approve or reject join requests, and delete a class.

Deleting a class removes no learner data: the class is marked deleted, its key stops working,
and its learners are asked to join a class again with a new key, keeping all their history.

## Repository layout

```
backend/     FastAPI service, Alembic migrations, the served model artefact, its tests
frontend/    React + TypeScript + Vite single-page app and its tests
notebooks/   The research work behind the model (exploration and model selection)
dataset/     Research dataset and feature matrices used by the pipeline
plan/        (outside this repo, in ../plan) build plans and the numbered decision log D1..D52
```

## Working on it

- **Branches.** Work on `dev`; `main` moves only through a pull request from `dev`.
- **Tests.** `backend/`: `pytest` (505 passing, plus live-database gates). `frontend/`:
  `npm test` (341 passing) and `npm run typecheck`.
- **Decisions.** Anything surprising in the behaviour is usually a recorded decision. Check
  `plan/README.md`'s decision table (D1–D52) before changing it.
