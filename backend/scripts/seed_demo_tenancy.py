"""Seed the demo tenancy -- `teacher01` and six classrooms (work order B6.3b-1).

WHY THIS SCRIPT TALKS HTTP AND NOT SQL
--------------------------------------
Every Component 3 reader of a student-application table filters `source_class = 'REAL'`
(`app/application/data_access.py`). A seeder that INSERTed into `b_learners`, `classrooms` or
`classroom_memberships` would therefore have to stamp its rows `'REAL'` to make them visible --
a falsehood in the exact column the whole provenance design rests on, in a project whose second
standing rule is that synthetic data never passes as anything else.

So this script creates nothing directly. It calls the student application's own HTTP API, and
the rows are `REAL` because the owning application genuinely created them. That is decision D26,
and it is the reason this file is full of HTTP plumbing rather than three INSERT statements.

The one table it does write is `t3_demo_learner_map` -- Component 3 owns that one -- and that
happens in phase two, not here.

PHASES
------
`--phase teacher`  (this work order, B6.3b-1)
    Supabase account -> `POST /teacher/profile` -> six classrooms -> six invite tokens.
    Small and fast, so the frontend login screen (frontend_plan.md section 11.0) becomes testable
    against real HTTP long before the 120 learners are provisioned.

`--phase learners`  (B6.3b-2, not implemented here)
    120 learner accounts, membership requests, approvals, and the `t3_demo_learner_map` bridge.

CREDENTIALS
-----------
Read from the environment only. Nothing is defaulted, nothing is logged, and the password is
never printed -- not in a banner, not in an error, not in the receipt. `backend/.env` is
gitignored (verified with `git check-ignore`), and that is where these belong.

    SUPABASE_URL                    https://<project>.supabase.co
    SUPABASE_SERVICE_ROLE_KEY       admin key -- creates the account with email_confirm=true so
                                    no real inbox is ever involved
    T3_DEMO_TEACHER_EMAIL           teacher01's sign-in address
    T3_DEMO_TEACHER_PASSWORD        teacher01's password
    T3_DEMO_TEACHER_NAME            display name written to teacher_profiles.name
    T3_STUDENT_API_BASE_URL         default http://127.0.0.1:8000

IDEMPOTENCE
-----------
Re-running must not create a second anything. Two separate mechanisms are needed because the
student app enforces two separate things:

  * `Idempotency-Key` is REQUIRED on every POST (a missing one is a 422, not a default). Keys are
    derived deterministically from the operation's identity and stored in the receipt, so a
    re-run replays the app's stored response instead of creating a duplicate.
  * The app also refuses duplicates on its own terms -- a second `POST /teacher/profile` for the
    same user is a 409, and a classroom name that collides case-insensitively for the same teacher
    is a 409. Those are treated as "already done, go and read it", never as failures.

INVITES ARE THE EXCEPTION, AND IT IS COUNTER-INTUITIVE
-----------------------------------------------------
`create_invite` does NOT refuse a second invite -- it mints a brand-new code and row every time.
So a DETERMINISTIC Idempotency-Key is exactly wrong here: it triggers an idempotency REPLAY, and
the stored replay body has `invite_token: null, token_already_issued: true`. The first run of this
script captured six usable codes; the second run replayed and overwrote all six with nulls, which
is how this was found.

Two consequences, both handled below:
  * The receipt is MERGED, never overwritten. A captured plaintext code is never replaced by a
    null, because only this file ever holds it -- the app stores a SHA-256 hash.
  * A classroom with no captured code gets a FRESH random Idempotency-Key, which issues a new
    usable invite. Codes expire 24h after issue, so learner seeding re-issues as a matter of
    course rather than treating expiry as an error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
import pathlib
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

# Load `backend/.env` the same file `Settings` reads, so this script and the API can never
# disagree about which Supabase project or database is in play. `override=False` means a value
# already exported in the shell still wins -- useful for a one-off run against a different
# target without editing the file. python-dotenv arrives with pydantic-settings; no new
# dependency.
_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]

# This script lives in backend/scripts/, so sys.path[0] is that directory and `import app`
# fails. Put the backend root first so the demo-map writer can reuse the project engine
# instead of opening a second, differently-configured connection.
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

load_dotenv(_BACKEND_ROOT / ".env", override=False)

# Deterministic namespace for Idempotency-Key derivation. A fixed namespace means the key for
# "create classroom 2A for this teacher" is the same on every run of this script, which is what
# makes a re-run a replay rather than a second create. A random namespace would defeat the
# entire mechanism while still looking correct.
_IDEMPOTENCY_NAMESPACE = uuid.UUID("6f3d1f8e-2c4a-4f5b-9d21-7e8a0b5c6d34")

#: D2 permits GRADE_2 and GRADE_3 only. Three of each -- a realistic split for a teacher who
#: takes both years. Names are the teacher's own labels, not analytics; change them freely.
DEFAULT_CLASSROOMS: tuple[tuple[str, str], ...] = (
    ("2A", "GRADE_2"),
    ("2B", "GRADE_2"),
    ("2C", "GRADE_2"),
    ("3A", "GRADE_3"),
    ("3B", "GRADE_3"),
    ("3C", "GRADE_3"),
)

_TIMEOUT = httpx.Timeout(20.0)

#: Supabase auth rate-limit handling. Bounded on purpose -- see `_supabase_post`.
_MAX_429_RETRIES = 8
_INITIAL_BACKOFF_SECONDS = 5.0
_MAX_BACKOFF_SECONDS = 120.0


class SeedError(RuntimeError):
    """A failure this script understands and can explain. Never carries a credential."""


@dataclass
class Receipt:
    """What later phases and `.env` read instead of re-deriving it.

    Deliberately carries no password and no access token: it is written to disk, and a receipt
    that quietly becomes a credential file is how secrets escape.
    """

    supabase_user_id: str | None = None
    supabase_subject: str | None = None
    teacher_email: str | None = None
    teacher_profile_id: str | None = None
    classrooms: list[dict[str, Any]] = field(default_factory=list)
    learners: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "supabase_user_id": self.supabase_user_id,
                "supabase_subject": self.supabase_subject,
                "teacher_email": self.teacher_email,
                "teacher_profile_id": self.teacher_profile_id,
                "classrooms": self.classrooms,
                "learners": self.learners,
            },
            indent=2,
            sort_keys=True,
        )


def idempotency_key(*parts: str) -> str:
    """A stable key for one logical operation.

    Reusing a key with a DIFFERENT body or path is a 409 in the student app, so the parts must
    identify the operation completely -- including the teacher, or two teachers creating a
    classroom called "2A" would collide on a key that describes only the name.
    """

    return str(uuid.uuid5(_IDEMPOTENCY_NAMESPACE, "|".join(parts)))


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SeedError(
            f"{name} is not set. This script reads every credential from the environment; "
            f"put it in backend/.env (gitignored) rather than passing it on the command line, "
            f"where it would land in your shell history."
        )
    return value


def _error_code(response: httpx.Response) -> str:
    """Pull `error.code` out of the student app's envelope.

    Its shape is `{"schema_version": ..., "error": {"code", "message", "request_id"}}` -- NOT
    FastAPI's `detail`. Reading `detail` here would make every error look like an unknown one.
    """

    try:
        body = response.json()
    except ValueError:
        return "UNPARSEABLE_BODY"
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        return str(body["error"].get("code", "UNKNOWN"))
    return "UNKNOWN"


def _supabase_post(
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
    what: str = "request",
) -> httpx.Response:
    """POST to Supabase, backing off on 429 instead of hammering it.

    Supabase rate-limits the auth endpoints per IP, and provisioning a classroom roster is
    exactly the shape of traffic that trips it -- this was found at learner 56 of 120. The
    server tells us how long to wait via `Retry-After` when it can; the exponential fallback
    covers the case where it does not.

    Deliberately bounded: after `_MAX_429_RETRIES` this raises rather than looping forever, so
    a genuinely exhausted quota surfaces as a clear failure the operator can act on rather than
    a script that appears to hang.
    """

    delay = _INITIAL_BACKOFF_SECONDS
    for attempt in range(_MAX_429_RETRIES + 1):
        response = client.post(url, headers=headers, json=json_body, params=params)
        if response.status_code != 429:
            return response
        if attempt == _MAX_429_RETRIES:
            break
        retry_after = response.headers.get("retry-after")
        try:
            wait = float(retry_after) if retry_after else delay
        except ValueError:
            wait = delay
        wait = min(max(wait, 1.0), _MAX_BACKOFF_SECONDS)
        print(f"    rate limited on {what}; waiting {wait:.0f}s (attempt {attempt + 1})")
        time.sleep(wait)
        delay = min(delay * 2, _MAX_BACKOFF_SECONDS)

    raise SeedError(
        f"Supabase kept returning 429 for {what} after {_MAX_429_RETRIES} retries. The project "
        f"auth quota is exhausted for now. Nothing is lost -- every learner provisioned so far "
        f"is in the receipt, so re-running later resumes from where this stopped."
    )


# ==========================================================================================
# Supabase -- account creation and sign-in.
# ==========================================================================================


def ensure_supabase_user(
    client: httpx.Client, *, supabase_url: str, service_role_key: str, email: str, password: str
) -> str:
    """Create teacher01's account if absent; return its user id either way.

    `email_confirm=True` is what keeps a real inbox out of the demo: without it Supabase leaves
    the account unconfirmed and the password grant fails with a message about confirmation that
    looks nothing like the actual problem.
    """

    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }
    response = _supabase_post(
        client,
        f"{supabase_url}/auth/v1/admin/users",
        headers=headers,
        json_body={"email": email, "password": password, "email_confirm": True},
        what="account creation",
    )
    if response.status_code in (200, 201):
        return str(response.json()["id"])

    # Already there. Supabase has used more than one shape for this over time, so match on the
    # body rather than on a status code alone.
    body_text = response.text.lower()
    if response.status_code in (409, 422) and (
        "already" in body_text or "exists" in body_text or "registered" in body_text
    ):
        found = _find_supabase_user_by_email(
            client, supabase_url=supabase_url, service_role_key=service_role_key, email=email
        )
        if found is None:
            raise SeedError(
                "Supabase reports the account already exists but it could not be listed back. "
                "Check that SUPABASE_SERVICE_ROLE_KEY belongs to the same project as SUPABASE_URL."
            )
        return found

    raise SeedError(
        f"Supabase admin user creation failed with HTTP {response.status_code}. "
        f"Confirm SUPABASE_SERVICE_ROLE_KEY is the service_role key, not the anon key."
    )


def _find_supabase_user_by_email(
    client: httpx.Client, *, supabase_url: str, service_role_key: str, email: str
) -> str | None:
    headers = {"apikey": service_role_key, "Authorization": f"Bearer {service_role_key}"}
    response = client.get(
        f"{supabase_url}/auth/v1/admin/users",
        headers=headers,
        params={"page": 1, "per_page": 200},
    )
    if response.status_code != 200:
        return None
    payload = response.json()
    users = payload.get("users", payload) if isinstance(payload, dict) else payload
    for user in users or []:
        if str(user.get("email", "")).lower() == email.lower():
            return str(user["id"])
    return None


def sign_in(
    client: httpx.Client, *, supabase_url: str, anon_or_service_key: str, email: str, password: str
) -> str:
    """Password grant -> access token. The token is returned, never logged or written to disk."""

    response = _supabase_post(
        client,
        f"{supabase_url}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": anon_or_service_key, "Content-Type": "application/json"},
        json_body={"email": email, "password": password},
        what="sign-in",
    )
    if response.status_code != 200:
        raise SeedError(
            f"Sign-in failed with HTTP {response.status_code}. The account exists only if "
            f"creation succeeded above; if this is 400, the password is wrong or the account "
            f"is unconfirmed."
        )
    token = response.json().get("access_token")
    if not token:
        raise SeedError("Sign-in returned no access_token.")
    return str(token)


# ==========================================================================================
# Student application -- teacher profile and classrooms.
# ==========================================================================================


def ensure_teacher_profile(
    client: httpx.Client, *, api_base: str, token: str, name: str
) -> dict[str, Any]:
    """Create the TEACHER profile, or read it back if it is already there.

    `app_users.profile_type` is set once and irreversibly by this endpoint -- a second call for
    the same user is a 409, which here means "already a teacher", not a failure.
    """

    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": idempotency_key("teacher-profile", name),
        "Content-Type": "application/json",
    }
    response = client.post(f"{api_base}/api/v1/teacher/profile", headers=headers, json={"name": name})
    if response.status_code in (200, 201):
        return response.json()
    if response.status_code == 409:
        existing = client.get(
            f"{api_base}/api/v1/teacher/profile", headers={"Authorization": f"Bearer {token}"}
        )
        if existing.status_code == 200:
            return existing.json()
    raise SeedError(
        f"Creating the teacher profile failed with HTTP {response.status_code} "
        f"(code {_error_code(response)})."
    )


def existing_classrooms(client: httpx.Client, *, api_base: str, token: str) -> dict[str, dict]:
    response = client.get(
        f"{api_base}/api/v1/classrooms", headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code != 200:
        raise SeedError(f"Listing classrooms failed with HTTP {response.status_code}.")
    # The app's uniqueness rule is case-insensitive and trimmed; match it exactly, or a re-run
    # would try to recreate "2a" alongside "2A" and take a 409 it does not expect.
    return {
        str(item.get("name") or "").strip().lower(): item
        for item in response.json().get("classrooms", [])
    }


def ensure_classroom(
    client: httpx.Client,
    *,
    api_base: str,
    token: str,
    teacher_profile_id: str,
    name: str,
    grade: str,
    already: dict[str, dict],
) -> tuple[dict[str, Any], bool]:
    """Return (classroom, created). `created` is False when it was already there."""

    key = name.strip().lower()
    if key in already:
        return already[key], False

    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": idempotency_key("classroom", teacher_profile_id, key),
        "Content-Type": "application/json",
    }
    response = client.post(
        f"{api_base}/api/v1/classrooms", headers=headers, json={"name": name, "grade": grade}
    )
    if response.status_code in (200, 201):
        return response.json(), True
    raise SeedError(
        f"Creating classroom {name!r} failed with HTTP {response.status_code} "
        f"(code {_error_code(response)})."
    )


def ensure_invite(
    client: httpx.Client, *, api_base: str, token: str, classroom_id: str, existing: str | None
) -> tuple[str, bool]:
    """Return (plaintext_code, reused). Never returns None.

    If `existing` holds a code this script captured earlier, it is returned untouched and no
    request is made -- re-running must not churn invites.

    Otherwise a FRESH random Idempotency-Key is used. A deterministic one would replay the
    stored response, whose `invite_token` is null by design, and the classroom would be left
    without a usable code. See the module docstring.
    """

    if existing:
        return existing, True

    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    response = client.post(
        f"{api_base}/api/v1/classrooms/{classroom_id}/invites", headers=headers
    )
    if response.status_code not in (200, 201):
        raise SeedError(
            f"Creating an invite for classroom {classroom_id} failed with HTTP "
            f"{response.status_code} (code {_error_code(response)})."
        )
    payload = response.json()
    code = payload.get("invite_token")
    if not code:
        raise SeedError(
            f"The invite for classroom {classroom_id} came back without a plaintext code "
            f"(token_already_issued={payload.get('token_already_issued')}). That means the "
            f"Idempotency-Key replayed a stored response; it must be fresh for every new invite."
        )
    return str(code), False


def load_receipt(path: Path) -> dict[str, Any]:
    """Previously captured state, or empty. Invite codes exist ONLY here."""

    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ==========================================================================================
# Learners (work order B6.3b-2).
# ==========================================================================================

#: Deterministic name pool. 30 x 4 = 120 distinct "Firstname I." labels, assigned by index so a
#: re-run produces the SAME name for the SAME learner. These are display labels a teacher reads;
#: the research id lives in `t3_demo_learner_map` and is never shown on screen.
_FIRST_NAMES = (
    "Amaya", "Nethmi", "Sahan", "Dilshan", "Kavindi", "Tharindu", "Ishara", "Ruwan",
    "Senuri", "Yasas", "Hiruni", "Chamod", "Nimali", "Pasindu", "Oshadi", "Kasun",
    "Tharushi", "Janith", "Sanduni", "Ravindu", "Imasha", "Dinuka", "Piumi", "Lakmal",
    "Nadeesha", "Supun", "Ayesha", "Bhanuka", "Malsha", "Kavisha",
)
_LAST_INITIALS = ("P.", "S.", "W.", "J.")

#: The demo map is not the output of a pipeline run, so it carries the nil UUID -- the same
#: convention `principal_resolution.DEMO_BINDING_PIPELINE_RUN_ID` uses for `t3_teacher_bindings`.
_DEMO_PIPELINE_RUN_ID = "00000000-0000-0000-0000-000000000000"


def learner_plan(
    classrooms: list[dict[str, Any]], per_class: int, email_pattern: str
) -> list[dict[str, Any]]:
    """Deterministic roster: index -> (email, name, classroom, research id).

    Determinism matters twice over. A re-run must address the SAME accounts rather than minting
    a second set, and the STU-xxxx assignment must be stable -- otherwise one run of analytics
    would attach to a different child than the next, which is the misattribution the unique
    constraints on `t3_demo_learner_map` exist to prevent.
    """

    plan: list[dict[str, Any]] = []
    index = 0
    for classroom in classrooms:
        for _ in range(per_class):
            first = _FIRST_NAMES[index % len(_FIRST_NAMES)]
            initial = _LAST_INITIALS[(index // len(_FIRST_NAMES)) % len(_LAST_INITIALS)]
            plan.append(
                {
                    "seq": index + 1,
                    "email": email_pattern.format(n=index + 1),
                    "name": f"{first} {initial}",
                    "classroom_id": classroom["classroom_id"],
                    "classroom_name": classroom["name"],
                    "invite_token": classroom["invite_token"],
                    # STU-0001 .. STU-0120; the research dataset numbers from 1.
                    "research_student_id": f"STU-{index + 1:04d}",
                }
            )
            index += 1
    return plan


def ensure_learner_profile(client: httpx.Client, *, api_base: str, token: str, name: str) -> str:
    """Create the LEARNER profile or read it back. Returns `learner_id`.

    As with the teacher profile, `profile_type` is set once and irreversibly, so a 409 means
    "already a learner", not a failure.
    """

    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": idempotency_key("learner-profile", name, token[-16:]),
        "Content-Type": "application/json",
    }
    response = client.post(
        f"{api_base}/api/v1/learner/profile", headers=headers, json={"name": name}
    )
    if response.status_code in (200, 201):
        return str(response.json()["learner_id"])
    if response.status_code == 409:
        existing = client.get(
            f"{api_base}/api/v1/learner/profile", headers={"Authorization": f"Bearer {token}"}
        )
        if existing.status_code == 200:
            return str(existing.json()["learner_id"])
    raise SeedError(
        f"Creating a learner profile failed with HTTP {response.status_code} "
        f"(code {_error_code(response)})."
    )


def request_membership(
    client: httpx.Client, *, api_base: str, token: str, invite_token: str
) -> tuple[str, str]:
    """Ask to join a classroom. Returns (membership_id, state).

    `/classroom-invites/resolve` is deliberately NOT called first: it is a preview step for the
    child, and this endpoint accepts the join code directly. Skipping it removes one request per
    learner and changes nothing about the outcome.
    """

    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": idempotency_key("membership-request", invite_token, token[-16:]),
        "Content-Type": "application/json",
    }
    response = client.post(
        f"{api_base}/api/v1/classroom-memberships/requests",
        headers=headers,
        json={"invite_token": invite_token},
    )
    if response.status_code in (200, 201):
        body = response.json()
        return str(body["classroom_membership_id"]), str(body["state"])
    raise SeedError(
        f"Membership request failed with HTTP {response.status_code} "
        f"(code {_error_code(response)})."
    )


def approve_membership(
    client: httpx.Client, *, api_base: str, teacher_token: str, membership_id: str
) -> str:
    """Teacher-side approval.

    A 409 means the membership is no longer PENDING -- approved on an earlier run -- which for a
    seeder is success, not an error.
    """

    headers = {
        "Authorization": f"Bearer {teacher_token}",
        "Idempotency-Key": idempotency_key("membership-approve", membership_id),
        "Content-Type": "application/json",
    }
    response = client.post(
        f"{api_base}/api/v1/classroom-memberships/{membership_id}/approve", headers=headers
    )
    if response.status_code in (200, 201):
        return str(response.json()["state"])
    if response.status_code == 409:
        return "ALREADY_DECIDED"
    raise SeedError(
        f"Approving membership {membership_id} failed with HTTP {response.status_code} "
        f"(code {_error_code(response)})."
    )


def write_demo_learner_map(database_url: str, pairs: list[tuple[str, str]]) -> int:
    """Upsert `learner_id -> STU-xxxx` into `t3_demo_learner_map`. Returns rows written.

    This is the ONE table this script writes directly, and it may because Component 3 owns it.
    `source_class` is SYNTHETIC because that is what the bridge is -- a demo artefact, not
    something the student application produced. Note this is also the provenance rule that would
    be WRONG for a student-app table, where REAL is required; the two families are opposites.
    """

    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.infrastructure.db.engine import create_direct_engine

    async def _run() -> int:
        engine, target = create_direct_engine(database_url)
        print(f"  demo-map target: {target}")
        maker = async_sessionmaker(engine, expire_on_commit=False)
        written = 0
        try:
            async with maker() as session:
                for learner_id, research_id in pairs:
                    await session.execute(
                        text(
                            "INSERT INTO t3_demo_learner_map "
                            "(learner_id, research_student_id, source_class, source_system, "
                            " parameter_source_status, pipeline_run_id) "
                            "VALUES (:lid, :sid, 'SYNTHETIC', 't3-demo-seed', "
                            "        'DEMO_ASSIGNED', :prid) "
                            "ON CONFLICT (learner_id) DO UPDATE "
                            "SET research_student_id = EXCLUDED.research_student_id"
                        ),
                        {"lid": learner_id, "sid": research_id, "prid": _DEMO_PIPELINE_RUN_ID},
                    )
                    written += 1
                await session.commit()
        finally:
            await engine.dispose()
        return written

    return asyncio.run(_run())


# ==========================================================================================
# Phase driver.
# ==========================================================================================


def seed_teacher_phase(*, dry_run: bool, receipt_path: Path) -> Receipt:
    supabase_url = _require_env("SUPABASE_URL").rstrip("/")
    service_role_key = _require_env("SUPABASE_SERVICE_ROLE_KEY")
    email = _require_env("T3_DEMO_TEACHER_EMAIL")
    password = _require_env("T3_DEMO_TEACHER_PASSWORD")
    display_name = os.environ.get("T3_DEMO_TEACHER_NAME", "Teacher01").strip() or "Teacher01"
    api_base = os.environ.get("T3_STUDENT_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

    planned = [
        (name, grade) for name, grade in DEFAULT_CLASSROOMS
    ]

    print(f"Supabase project : {supabase_url}")
    print(f"Student API      : {api_base}")
    print(f"Teacher          : {email}  (display name {display_name!r})")
    print(f"Classrooms       : {', '.join(f'{n} [{g}]' for n, g in planned)}")

    if dry_run:
        print("\n--dry-run: nothing was created. Re-run without it to apply.")
        return Receipt(teacher_email=email)

    receipt = Receipt(teacher_email=email)

    # Codes captured by an earlier run exist ONLY here -- the app keeps a SHA-256 hash. Load
    # them before doing anything, or this run overwrites them with nulls.
    prior = load_receipt(receipt_path)
    prior_codes = {
        str(entry.get("classroom_id")): entry.get("invite_token")
        for entry in prior.get("classrooms", [])
        if entry.get("invite_token")
    }
    if prior_codes:
        print(f"Recovered {len(prior_codes)} invite code(s) from the previous receipt.")

    with httpx.Client(timeout=_TIMEOUT) as client:
        user_id = ensure_supabase_user(
            client,
            supabase_url=supabase_url,
            service_role_key=service_role_key,
            email=email,
            password=password,
        )
        receipt.supabase_user_id = user_id
        # Supabase's user id IS the `sub` claim, which is what `app_users.supabase_subject`
        # stores and what `resolve_principal` matches on. Recording both names because the two
        # halves of this system call the same value different things.
        receipt.supabase_subject = user_id
        print(f"\nSupabase account ready (id {user_id}).")

        # The password grant is a CLIENT call: it presents the publishable (anon) key, not
        # the admin key. Falling back to the secret key works, but sending an admin
        # credential on a client-shaped request is a habit worth not forming.
        token = sign_in(
            client,
            supabase_url=supabase_url,
            anon_or_service_key=os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
            or service_role_key,
            email=email,
            password=password,
        )
        print("Signed in; access token acquired (not logged).")

        profile = ensure_teacher_profile(
            client, api_base=api_base, token=token, name=display_name
        )
        teacher_profile_id = str(profile["teacher_profile_id"])
        receipt.teacher_profile_id = teacher_profile_id
        print(f"Teacher profile  : {teacher_profile_id}")

        already = existing_classrooms(client, api_base=api_base, token=token)
        for name, grade in planned:
            classroom, created = ensure_classroom(
                client,
                api_base=api_base,
                token=token,
                teacher_profile_id=teacher_profile_id,
                name=name,
                grade=grade,
                already=already,
            )
            classroom_id = str(classroom["classroom_id"])
            invite_code, reused = ensure_invite(
                client,
                api_base=api_base,
                token=token,
                classroom_id=classroom_id,
                existing=prior_codes.get(classroom_id),
            )
            receipt.classrooms.append(
                {
                    "classroom_id": classroom_id,
                    "name": name,
                    "grade": grade,
                    "invite_token": invite_code,
                }
            )
            state = "created" if created else "already present"
            invite_state = "invite code reused" if reused else "new invite code issued"
            print(f"  {name:<4} [{grade}] {state}; {invite_state}")

    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(receipt.to_json(), encoding="utf-8")
    print(f"\nReceipt written to {receipt_path}")
    print(
        "\nNext: put this in backend/.env so the API can resolve the demo teacher --\n"
        f"  T3_DEMO_TEACHER_POOL={receipt.teacher_profile_id}\n"
        "  (only needed if T3_DEMO_MODE=true; under D29 the login path does not require it)"
    )
    return receipt



def seed_learners_phase(*, per_class: int, dry_run: bool, receipt_path: Path) -> None:
    """Provision `per_class` learners into each of teacher01 classrooms (work order B6.3b-2).

    Depends on `--phase teacher` having run: the classroom ids and, critically, the plaintext
    join codes live only in the receipt.
    """

    supabase_url = _require_env("SUPABASE_URL").rstrip("/")
    service_role_key = _require_env("SUPABASE_SERVICE_ROLE_KEY")
    publishable_key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip() or service_role_key
    teacher_email = _require_env("T3_DEMO_TEACHER_EMAIL")
    teacher_password = _require_env("T3_DEMO_TEACHER_PASSWORD")
    learner_password = _require_env("T3_DEMO_LEARNER_PASSWORD")
    email_pattern = os.environ.get(
        "T3_DEMO_LEARNER_EMAIL_PATTERN", "c3demo.learner{n:03d}@example.com"
    )
    api_base = os.environ.get("T3_STUDENT_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    database_url = _require_env("DATABASE_URL")

    prior = load_receipt(receipt_path)
    classrooms = prior.get("classrooms") or []
    if not classrooms:
        raise SeedError(
            "No classrooms in the receipt. Run `--phase teacher` first -- the classroom ids and "
            "the plaintext join codes exist nowhere else."
        )
    missing = [c["name"] for c in classrooms if not c.get("invite_token")]
    if missing:
        raise SeedError(
            f"No usable join code for classroom(s) {', '.join(missing)}. The app stores only a "
            f"SHA-256 hash, so the plaintext cannot be recovered -- delete those entries from the "
            f"receipt and re-run `--phase teacher` to mint fresh invites."
        )

    plan = learner_plan(classrooms, per_class, email_pattern)
    done = {entry["email"]: entry for entry in prior.get("learners", []) if entry.get("learner_id")}

    print(f"Student API : {api_base}")
    print(f"Classrooms  : {len(classrooms)} x {per_class} learners = {len(plan)} total")
    print(f"Email shape : {email_pattern.format(n=1)}")
    print(f"Already done: {len(done)}")

    if dry_run:
        print("\n--dry-run: nothing was created. Re-run without it to apply.")
        return

    receipt = Receipt(
        supabase_user_id=prior.get("supabase_user_id"),
        supabase_subject=prior.get("supabase_subject"),
        teacher_email=prior.get("teacher_email"),
        teacher_profile_id=prior.get("teacher_profile_id"),
        classrooms=classrooms,
    )

    created = reused = 0
    with httpx.Client(timeout=_TIMEOUT) as client:
        teacher_token = sign_in(
            client,
            supabase_url=supabase_url,
            anon_or_service_key=publishable_key,
            email=teacher_email,
            password=teacher_password,
        )
        print("Teacher signed in.\n")

        for item in plan:
            existing = done.get(item["email"])
            if existing:
                receipt.learners.append(existing)
                reused += 1
                continue

            user_id = ensure_supabase_user(
                client,
                supabase_url=supabase_url,
                service_role_key=service_role_key,
                email=item["email"],
                password=learner_password,
            )
            learner_token = sign_in(
                client,
                supabase_url=supabase_url,
                anon_or_service_key=publishable_key,
                email=item["email"],
                password=learner_password,
            )
            learner_id = ensure_learner_profile(
                client, api_base=api_base, token=learner_token, name=item["name"]
            )
            membership_id, _ = request_membership(
                client,
                api_base=api_base,
                token=learner_token,
                invite_token=item["invite_token"],
            )
            state = approve_membership(
                client,
                api_base=api_base,
                teacher_token=teacher_token,
                membership_id=membership_id,
            )
            receipt.learners.append(
                {
                    "seq": item["seq"],
                    "email": item["email"],
                    "name": item["name"],
                    "supabase_user_id": user_id,
                    "learner_id": learner_id,
                    "classroom_id": item["classroom_id"],
                    "classroom_name": item["classroom_name"],
                    "membership_id": membership_id,
                    "membership_state": state,
                    "research_student_id": item["research_student_id"],
                }
            )
            created += 1
            if created % 10 == 0:
                print(f"  provisioned {created} new learner(s)...")
            # Write through often: 120 accounts is a long run, and losing the receipt halfway
            # would orphan every Supabase account created so far.
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(receipt.to_json(), encoding="utf-8")

    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(receipt.to_json(), encoding="utf-8")
    print(f"\nLearners: {created} created, {reused} already present.")

    pairs = [
        (entry["learner_id"], entry["research_student_id"])
        for entry in receipt.learners
        if entry.get("learner_id")
    ]
    written = write_demo_learner_map(database_url, pairs)
    print(f"t3_demo_learner_map: {written} row(s) upserted.")
    print(f"Receipt written to {receipt_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed the Component 3 demo tenancy through the student application's API."
    )
    parser.add_argument(
        "--phase",
        choices=("teacher", "learners"),
        default="teacher",
        help="'teacher' seeds teacher01 and six classrooms (B6.3b-1). "
        "'learners' provisions the roster and the demo bridge (B6.3b-2).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done and exit without creating anything.",
    )
    parser.add_argument(
        "--per-class",
        type=int,
        default=20,
        help="Learners per classroom for --phase learners (default 20 -> 120 across six).",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=Path(__file__).resolve().parent / "demo_tenancy_receipt.json",
        help="Where to write the JSON receipt later phases read.",
    )
    args = parser.parse_args(argv)

    try:
        if args.phase == "learners":
            seed_learners_phase(
                per_class=args.per_class, dry_run=args.dry_run, receipt_path=args.receipt
            )
        else:
            seed_teacher_phase(dry_run=args.dry_run, receipt_path=args.receipt)
    except SeedError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(
            f"\nFAILED: could not reach a required service ({type(exc).__name__}). "
            f"Is the student application's API container running? "
            f"`docker compose up -d api` in Upadya/Dev/backend.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
