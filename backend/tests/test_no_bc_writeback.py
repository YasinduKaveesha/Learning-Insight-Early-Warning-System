"""D10: Component 3 is read-only toward Components B and C (work order B3.5, gate 8).

No source file under `backend/app/` may contain a write path toward a Component B or C
table -- no `INSERT` / `UPDATE` / `DELETE` (SQL or SQLAlchemy Core) against any `b_*` or
`c_*` table. The recommendation schema (B3.5) carries `b_applied_at_intervention_session` /
`c_applied_at_intervention_session` columns that stay NULL for all of v1; there must be no
code -- not disabled, not feature-flagged, not a stub -- that would populate a running
Component B or C session (`backend_plan.md` section 11).

Standard library only; runs in the pinned `c3-ews` env.
"""

from __future__ import annotations

import re
from pathlib import Path

_APP = Path(__file__).resolve().parents[1] / "app"

# SQL write verbs against a b_/c_ prefixed table name, in a string literal or raw SQL.
_SQL_WRITE = re.compile(
    r"(insert\s+into|update|delete\s+from)\s+[\"']?[bc]_[a-z_]+",
    re.IGNORECASE,
)
# SQLAlchemy Core: `b_something.insert()` / `.update()` / `.delete()`, or
# `insert(b_something)` / `update(c_something)`.
_CORE_WRITE = re.compile(
    r"\b[bc]_[a-z_]+\s*\.\s*(insert|update|delete)\s*\(|"
    r"\b(insert|update|delete)\s*\(\s*[bc]_[a-z_]+",
    re.IGNORECASE,
)

# `b_learners` / `classrooms` shadows are one-column Table() stand-ins for a foreign key
# only; they are never the subject of a write. Flag anything that looks otherwise.


def _offending_lines() -> list[str]:
    hits: list[str] = []
    for path in sorted(_APP.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _SQL_WRITE.search(line) or _CORE_WRITE.search(line):
                hits.append(f"{path.relative_to(_APP.parent)}:{lineno}: {line.strip()}")
    return hits


def test_no_write_path_toward_component_b_or_c_tables() -> None:
    offending = _offending_lines()
    assert not offending, "D10 violated -- write path toward a b_/c_ table:\n" + "\n".join(
        offending
    )
