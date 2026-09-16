"""Human-readable, portable projections of the ledger.

Per docs/02-state-and-memory.md: "SQLite este sursa tranzacțională... Nu
folosim fișiere JSONL drept singurul adevăr." These exports are read-only
projections for humans and for portable backup, never a second source of
truth -- restoring from them means replaying the underlying events, not
importing these files directly.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path


def export_state(conn: sqlite3.Connection, out_dir: str | Path) -> None:
    """Write current projections as JSON and a daily episodic journal as
    Markdown into out_dir/state/ and out_dir/journal/."""

    out_dir = Path(out_dir)
    state_dir = out_dir / "state"
    journal_dir = out_dir / "journal"
    state_dir.mkdir(parents=True, exist_ok=True)
    journal_dir.mkdir(parents=True, exist_ok=True)

    _export_table_json(conn, "tasks", state_dir / "tasks.json")
    _export_table_json(conn, "approvals", state_dir / "approvals.json")
    _export_table_json(conn, "memory_candidates", state_dir / "memory_candidates.json")
    _export_journal(conn, journal_dir)


def _export_table_json(conn: sqlite3.Connection, table: str, out_path: Path) -> None:
    cursor = conn.execute(f"SELECT * FROM {table}")
    columns = [d[0] for d in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    out_path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _export_journal(conn: sqlite3.Connection, journal_dir: Path) -> None:
    rows = conn.execute(
        "SELECT occurred_at, type, source, payload FROM events ORDER BY rowid_order"
    ).fetchall()

    by_day: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    for occurred_at, type_, source, payload in rows:
        day = occurred_at[:10]  # YYYY-MM-DD prefix of an ISO 8601 timestamp
        by_day[day].append((occurred_at, type_, source, payload))

    for day, day_rows in by_day.items():
        lines = [f"# {day}", ""]
        for occurred_at, type_, source, payload in day_rows:
            lines.append(f"- `{occurred_at}` **{type_}** ({source}): {payload}")
        (journal_dir / f"{day}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
