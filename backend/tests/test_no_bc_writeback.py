"""D10: Component 3 is read-only toward Components B and C (work order B3.5, gate 8;
extended by work order B2.3's gate 10 to name the specific student-app identity tables
`resolve_principal` reads through).

No source file under `backend/app/` may contain a write path toward a Component B or C
table -- no `INSERT` / `UPDATE` / `DELETE` (SQL or SQLAlchemy Core) against any `b_*` or
`c_*` table, nor against `app_users`, `teacher_profiles`, or `classrooms` specifically (B2.3:
a missing `app_users`/`teacher_profiles` row during principal resolution is ALWAYS a 403,
never an insert -- Component 3 does not provision student-app identity rows; that is the
student app's exclusive job). The recommendation schema (B3.5) carries
`b_applied_at_intervention_session` / `c_applied_at_intervention_session` columns that stay
NULL for all of v1; there must be no code -- not disabled, not feature-flagged, not a stub --
that would populate a running Component B or C session (`backend_plan.md` section 11).

Standard library only; runs in the pinned `c3-ews` env.
"""

from __future__ import annotations

import re
from pathlib import Path

_APP = Path(__file__).resolve().parents[1] / "app"

# Table-name alternation shared by both regexes below: every b_*/c_* prefixed name, plus the
# three student-app identity tables B2.3's gate 10 names explicitly by name (none of them
# happen to start with b_/c_, so the prefix pattern alone would miss them).
_TABLE_ALTERNATION = r"(?:[bc]_[a-z_]+|app_users|teacher_profiles|classrooms)"

# SQL write verbs against a protected table name, in a string literal or raw SQL.
_SQL_WRITE = re.compile(
    rf"(insert\s+into|update|delete\s+from)\s+[\"']?{_TABLE_ALTERNATION}\b",
    re.IGNORECASE,
)
# SQLAlchemy Core: `b_something.insert()` / `.update()` / `.delete()`, or
# `insert(b_something)` / `update(c_something)` / `insert(app_users)` / etc.
_CORE_WRITE = re.compile(
    rf"\b{_TABLE_ALTERNATION}\s*\.\s*(insert|update|delete)\s*\(|"
    rf"\b(insert|update|delete)\s*\(\s*{_TABLE_ALTERNATION}\b",
    re.IGNORECASE,
)

# `b_learners` / `classrooms` / `app_users` / `teacher_profiles` shadows are narrow Table()
# stand-ins for a foreign key or a read-only lookup only; they are never the subject of a
# write. Flag anything that looks otherwise.


def _offending_lines() -> list[str]:
    hits: list[str] = []
    for path in sorted(_APP.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _SQL_WRITE.search(line) or _CORE_WRITE.search(line):
                hits.append(f"{path.relative_to(_APP.parent)}:{lineno}: {line.strip()}")
    return hits


def test_no_write_path_toward_component_b_or_c_tables() -> None:
    offending = _offending_lines()
    assert not offending, (
        "D10 violated -- write path toward a b_/c_/app_users/teacher_profiles/classrooms "
        "table:\n" + "\n".join(offending)
    )
