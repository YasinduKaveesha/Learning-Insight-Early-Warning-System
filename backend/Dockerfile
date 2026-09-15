# Component 3 backend -- container image.
#
# PYTHON 3.11, NOT NEWER. The served model artefact
# (artefacts/1.0.0/nb05_primary_logreg_armA.joblib) was fitted under Python 3.11 with the
# scikit-learn pinned in requirements.txt (D18). joblib loads a mismatched build with only a
# warning and then predicts differently, so the version is part of the contract, not a
# preference. The host `c3-ews` conda env is the same 3.11.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so editing application code does not reinstall scikit-learn/numpy.
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# The application, its migrations and the serving artefact store. `tests` and `scripts` come
# too: the live gates and the demo seeder are run with `docker compose run`, and leaving them
# out would mean two different images for one codebase.
COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 migrations ./migrations
COPY --chown=10001:10001 scripts ./scripts
COPY --chown=10001:10001 tests ./tests
COPY --chown=10001:10001 artefacts ./artefacts
COPY --chown=10001:10001 alembic.ini pytest.ini ./

# Non-root, matching the student app's own image (uid 10001). Nothing here writes to disk.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin t3
USER 10001

EXPOSE 8100

# Overridden by compose for local development (which adds --reload).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100", "--no-access-log"]
