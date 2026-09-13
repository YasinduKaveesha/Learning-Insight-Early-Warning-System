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
load_dotenv(pathlib.Path(__file__).resolve().parents[1] / ".env", override=False)

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

    def to_json(self) -> str:
        return json.dumps(
            {
                "supabase_user_id": self.supabase_user_id,
                "supabase_subject": self.supabase_subject,
                "teacher_email": self.teacher_email,
                "teacher_profile_id": self.teacher_profile_id,
                "classrooms": self.classrooms,
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
    response = client.post(
        f"{supabase_url}/auth/v1/admin/users",
        headers=headers,
        json={"email": email, "password": password, "email_confirm": True},
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

    response = client.post(
        f"{supabase_url}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": anon_or_service_key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed the Component 3 demo tenancy through the student application's API."
    )
    parser.add_argument(
        "--phase",
        choices=("teacher", "learners"),
        default="teacher",
        help="'teacher' seeds teacher01 and six classrooms (B6.3b-1). "
        "'learners' is B6.3b-2 and is not implemented yet.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done and exit without creating anything.",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=Path(__file__).resolve().parent / "demo_tenancy_receipt.json",
        help="Where to write the JSON receipt later phases read.",
    )
    args = parser.parse_args(argv)

    if args.phase == "learners":
        print(
            "Phase 'learners' (B6.3b-2) is not implemented in this work order. It provisions "
            "120 learner accounts, their membership requests and approvals, and the "
            "t3_demo_learner_map bridge.",
            file=sys.stderr,
        )
        return 2

    try:
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
