# Component 3 backend

FastAPI backend for the Learning Insight & Early Warning System (R26-IT-138). See
`../../plan/backend_plan.md` for the full build plan; this README covers only local setup.

## Scope of this build

Build-order steps 1 (scaffold), 3 (model loading) and 4 (feature builder) only. No database,
no auth, no business endpoints -- those are later work orders.

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
# edit .env -- DATABASE_URL and SUPABASE_* come from Upadya/Dev/backend/.env (same project);
# everything else is this backend's own.
```

## Run

```bash
uvicorn app.main:app --port 8100 --reload
```

`GET /health/live` and `GET /health/ready` (model-artefact status only for this build).

## Test

```bash
pytest
```

Run the golden vector first (`tests/test_golden_vector.py`) -- if it does not reproduce,
feature construction is wrong; fix that before trusting anything else.
