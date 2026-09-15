# Learning Insight & Early Warning System -- backend

FastAPI backend for the Learning Insight & Early Warning System (R26-IT-138). It serves the
teacher's dashboard: it runs the model over learner activity, keeps the suggestions and the
teacher's decisions on them, and answers every read the dashboard makes.

See the [repository README](../README.md) for how the pieces fit together and
`../../plan/backend_plan.md` for the full build plan.

## What it owns, and what it must never touch

It owns the `t3_*` tables: pipeline runs, the panel, features, predictions, suggestions and
their decisions, and class keys.

Everything about accounts, learners, classes and memberships belongs to the **student app**,
a separate backend owned by another team. This service reads those tables and **never writes
them** — a test (`tests/test_no_bc_writeback.py`) scans the source and fails the build if any
write to them appears. Creating a class, approving a join request or deleting a class goes
through the student app's own API, called by the frontend.

The two backends share one Postgres server so those reads are possible; they are still two
separate services, images and compose projects.

## Its API

All under `/api/v1/t3`, all requiring a teacher's Supabase token:

| Read | |
|---|---|
| `GET /home` | Counts and the teacher's classes |
| `GET /watch`, `GET /classes/{id}/watch` | Learners worth a closer look |
| `GET /classes/{id}/cohort` | One class's roster with each learner's status |
| `GET /students/{id}`, `/sessions`, `/skills` | One learner in detail |
| `GET /classes/{id}/reports` | Class-level charts |
| `GET /students/{id}/recommendations` | Suggested next steps for that learner |

| Write | |
|---|---|
| `POST /recommendations/{id}/accept`, `/modify`, `/dismiss` | The teacher's decision, saved as research data |
| `POST /classes/{id}/key` | Store a new class's key, proved against the student app's invite |

`GET /health/live` and `GET /health/ready`. Ready means the model artefact loaded with its
SHA-256 verified and the database answered.

A saved decision never changes what the student app teaches a child. It is a record of what
the teacher chose.

## Environment

The model artefact was pickled under scikit-learn 1.9.0 / numpy 2.4.6 / scipy 1.17.1 / Python
3.11 (decision D18). Loading it under a different scikit-learn version raises only a warning
while silently altering numerics, so the version is asserted explicitly at load time and in
`tests/test_model_loading.py`.

Recreate the producing conda environment from the repo-root `environment.yml`, with
scikit-learn pinned:

```bash
conda env create -n c3-ews -f ../../environment.yml
conda install -n c3-ews -c conda-forge "scikit-learn=1.9.0" "numpy=2.4.6" "scipy=1.17.1"
conda run -n c3-ews pip install -r requirements.txt
```

If you see a native crash (`0xC06D007F`) with no traceback while running anything from this
environment, it is MKL BLAS, not a code or data bug:

```bash
conda install -n c3-ews -c conda-forge --solver=libmamba "libblas=*=*openblas"
```

## Populate the artefact store

The versioned artefact store lives at `backend/artefacts/<model_version>/`. The active version
(`1.0.0`) is already committed here, copied from
`../notebooks/outputs/models/nb05_primary_logreg_armA.joblib` (that directory is
`.gitignore`d upstream and not reproducible from a clone, so service code never references it
directly). To repopulate after a model refresh:

```bash
mkdir -p artefacts/<new_version>
cp ../notebooks/outputs/models/nb05_primary_logreg_armA.joblib artefacts/<new_version>/
```

Then update `T3_ACTIVE_MODEL_VERSION` and the expected SHA-256
(`app/infrastructure/model_loading.py::ARTEFACT_SHA256`) together, and re-run the golden vector
test before anything else.

## Configure

```bash
cp .env.example .env
# edit .env -- DATABASE_URL and SUPABASE_* match the student app's own .env (same project);
# everything else is this backend's own.
```

## Run

### In Docker (recommended)

This backend and the student app's backend are two separate services with two separate
images and two separate compose projects. They share only the Postgres server, because this
one reads the student app's roster tables. Start that stack first, so the database and its
network exist:

```bash
docker compose up -d db api      # in the STUDENT APP repository, first
docker compose up -d --build     # here, in backend/ -- this backend, on :8100
docker compose logs -f api       # follow it
docker compose down              # stop it; leaves the student app running
```

`compose.yaml` joins the student stack's existing network as an **external** network, so
`db:5432` resolves without the host proxy, and a missing student stack fails loudly instead
of starting an API with no data behind it. `.env` is read at run time and is never copied
into the image (it holds the Supabase service-role key); only `DATABASE_URL` is overridden,
from the host's `127.0.0.1:55432` to the in-network `db:5432`.

The source tree is mounted read-only with `--reload`, so an edit on the host restarts the
container. The serving artefact is baked into the image, not mounted.

### On the host

Still the right way to run the test suite, the loader and Alembic, because the pinned
`c3-ews` conda env lives here. It reaches Postgres on `127.0.0.1:55432`, which needs the
proxy container:

```bash
docker run -d --name c3-pgproxy --network upadya-be1_default \
  -p 127.0.0.1:55432:5432 alpine/socat \
  tcp-listen:5432,fork,reuseaddr tcp-connect:db:5432
uvicorn app.main:app --port 8100 --reload
```

Run the API either in Docker or on the host, not both: they would fight over port 8100.

`GET /health/live` and `GET /health/ready` (model-artefact status only for this build).

## Test

```bash
pytest
```

Run the golden vector first (`tests/test_golden_vector.py`) -- if it does not reproduce,
feature construction is wrong; fix that before trusting anything else.

## Live database gates (work order B0.1)

Four test files reach a real Postgres and are skipped whole unless `T3_LIVE_DB_URL` is set
and the `c3-ews` env has the DB deps installed: `test_t3_live_schema.py`, `test_t3_loader.py`
(its end-to-end case), `test_t3_predictions_live.py`, `test_t3_recommendations_live.py`.

### 1. Install the pinned DB deps into `c3-ews`

```powershell
conda run -n c3-ews python -m pip install "alembic==1.16.4" "SQLAlchemy==2.0.43" "asyncpg==0.30.0"
```

These are already pinned in `requirements.txt`; this just gets them into the conda env
(pip-installed, not conda-installed -- do not let this bump scikit-learn).

### 2. Bring the database up with a published port

The student app's `compose.yaml` (owned by another team) deliberately does not publish the
`db` service's port -- the `c3-ews` env runs on the host, not in a container, so it cannot
reach an unpublished port. This repository adds a port with a separate, opt-in override file
instead of editing that compose file:

```powershell
Set-Location "<the student app repository>\backend"
docker compose -f compose.yaml -f "...\Learning-Insight-Early-Warning-System\backend\docker\compose.c3-test-db.yaml" up -d db
```

This publishes `db` on `127.0.0.1:55432` only while the override `-f` is passed. A plain
`docker compose up` (no override) never publishes a port. Verify either state with
`docker port upadya-be1-db-1`.

### 3. THE TARGET DATABASE IS `upadya_test`, NEVER `upadya`

`upadya` is the student app's live-looking dev database -- the one this backend's own tests,
Alembic downgrades, and the loader would happily wipe or corrupt if pointed at it (this
project has already had a shared database wiped once). `upadya_test` is a separate, disposable
database on the same Postgres server, created once via
`CREATE DATABASE upadya_test OWNER upadya;` and intended to be migrated, mutated and reset
freely. Every live test file, and the loader's manual invocation, must target it:

```
T3_LIVE_DB_URL=postgresql://upadya:local-development-only@127.0.0.1:55432/upadya_test
```

A shared guard, `tests/_live_db_target_guard.py`, enforces this: every live test module calls
`assert_safe_live_target(T3_LIVE_DB_URL)` before any test in it can run. It refuses (printing
the REDACTED host/db first) if the URL names any database other than `upadya_test`, or if it
looks like the Supabase transaction pooler (port 6543 or a `pooler` host). This is a test-only
module and does not affect `app/infrastructure/migration_guard.py` or `migrations/env.py`.

### 4. Migrate `upadya_test` to head

```powershell
Set-Location "...\Learning-Insight-Early-Warning-System\backend"
$env:DATABASE_URL = "postgresql://upadya:local-development-only@127.0.0.1:55432/upadya_test"
conda run -n c3-ews python -m alembic upgrade head
```

### 5. Run the live gates

```powershell
$env:T3_LIVE_DB_URL = "postgresql://upadya:local-development-only@127.0.0.1:55432/upadya_test"
conda run -n c3-ews python -m pytest -q --no-header
```

The four DB test files now run instead of skipping. Only the full-dataset golden-vector test
(`T3_RESEARCH_PANEL_PATH` unset) still skips by design.

### Known gap: the loader's default resolver has no live match in `upadya_test`

`app/application/t3_loader.SqlLearnerResolver` matches the research dataset's `student_id`
(`"STU-0001"`, ...) against `b_learners.name` by default -- documented in its own docstring as
"the seam" for live-integration wiring, not yet connected. `upadya_test`'s `b_learners.name`
values are unrelated test-fixture names, so running
`python -m app.application.t3_loader` (or `SqlLearnerResolver` at all) against `upadya_test`
today aborts with `LearnerResolutionError` for all 300 research learners -- correctly, and
with zero panel rows written, but it means the "`t3_panel` has exactly 7,500 rows" demonstration
cannot be produced against this database as currently seeded. Wiring a real correspondence (or
seeding 300 matching `b_learners` rows in `upadya_test`) is a live-integration / fixture-data
decision outside this work order's scope (no application logic, no schema change) -- see the
B0.1 report for the smaller-scale demonstration used in its place.
