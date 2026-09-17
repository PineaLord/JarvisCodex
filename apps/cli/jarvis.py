#!/usr/bin/env python3
"""Local CLI adapter. See docs/06-roadmap.md Faza B.

A thin shell around core/conversation.py and the storage/policy layers --
a future Telegram adapter should call the same functions rather than grow
its own copy of this logic.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backends.factory import get_backend  # noqa: E402
from contracts.models import Event  # noqa: E402
from core.conversation import handle_message  # noqa: E402
from core.initiative import run_heartbeat  # noqa: E402
from storage.migrate import MIGRATIONS_DIR, applied_migrations  # noqa: E402
from storage.sqlite_store import SqliteEventStore, connect  # noqa: E402


def _db_path() -> Path:
    data_dir = Path(os.environ.get("JARVIS_CODEX_DATA_DIR", "./data/live"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "jarvis.db"


def cmd_chat(args: argparse.Namespace) -> int:
    conn = connect(_db_path())
    reply = handle_message(conn, get_backend(), args.session, args.text)
    conn.close()
    print(reply)
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    conn = connect(_db_path())
    counts = {
        "events": conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
        "tasks_open": conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'open'").fetchone()[0],
        "approvals_pending": conn.execute("SELECT COUNT(*) FROM approvals WHERE status = 'pending'").fetchone()[0],
        "memory_candidates": conn.execute("SELECT COUNT(*) FROM memory_candidates").fetchone()[0],
        "signals": conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0],
        "initiatives_proposed": conn.execute("SELECT COUNT(*) FROM initiatives WHERE status = 'proposed'").fetchone()[0],
        "goals_active": conn.execute("SELECT COUNT(*) FROM goals WHERE status = 'active'").fetchone()[0],
    }
    conn.close()
    print(json.dumps(counts, indent=2))
    return 0


def cmd_approvals_list(_args: argparse.Namespace) -> int:
    conn = connect(_db_path())
    rows = conn.execute(
        "SELECT id, level, description, expires_at FROM approvals WHERE status = 'pending' ORDER BY id"
    ).fetchall()
    conn.close()
    if not rows:
        print("No pending approvals.")
        return 0
    for id_, level, description, expires_at in rows:
        print(f"{id_}  [{level}]  expires {expires_at}\n    {description}")
    return 0


def cmd_approvals_decide(args: argparse.Namespace) -> int:
    conn = connect(_db_path())
    store = SqliteEventStore(conn)

    store.append(Event(
        id=f"evt-decide-{args.approval_id}-{int(datetime.now(timezone.utc).timestamp())}",
        schema_version=1,
        occurred_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        type="approval.decided",
        source="cli",
        payload={"approval_id": args.approval_id, "decision": args.decision},
    ))
    conn.close()
    print(f"Approval {args.approval_id} marked {args.decision}.")
    return 0


def cmd_healthcheck(_args: argparse.Namespace) -> int:
    report = {}
    try:
        conn = connect(_db_path())
        all_migrations = {p.name for p in MIGRATIONS_DIR.glob("*.sql")}
        pending = all_migrations - applied_migrations(conn)
        report["database"] = "ok"
        report["migrations_pending"] = sorted(pending)
        conn.close()
    except Exception as e:  # narrow to reporting, not masking real failures
        report["database"] = f"error: {e}"

    report["age_available"] = shutil.which("age") is not None
    ok = report["database"] == "ok" and not report["migrations_pending"]
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


def cmd_heartbeat(args: argparse.Namespace) -> int:
    conn = connect(_db_path())
    summary = run_heartbeat(conn, daily_quota=args.daily_quota)
    conn.close()
    print(summary)
    return 0


def cmd_kill(_args: argparse.Namespace) -> int:
    # Per docs/04-safety-model.md, /kill bypasses the LLM, scheduler and
    # queue and stops only job process trees -- not the control plane.
    # Heartbeat (Faza C) runs as a short-lived one-shot invocation, not a
    # persistent job supervisor with process trees to kill, so there is
    # genuinely nothing to stop yet: an honest no-op, not a placeholder
    # that pretends to do something it can't.
    print("No running job process trees to stop yet -- heartbeat runs one-shot (Faza C).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis")
    sub = parser.add_subparsers(dest="command", required=True)

    p_chat = sub.add_parser("chat", help="Send a message to the reasoning backend")
    p_chat.add_argument("session", help="Session id, e.g. a username or conversation label")
    p_chat.add_argument("text", help="What you want to say")
    p_chat.set_defaults(func=cmd_chat)

    p_status = sub.add_parser("status", help="Show ledger/approval/memory counts")
    p_status.set_defaults(func=cmd_status)

    p_approvals = sub.add_parser("approvals", help="List or decide pending approvals")
    approvals_sub = p_approvals.add_subparsers(dest="approvals_command", required=True)
    p_list = approvals_sub.add_parser("list", help="List pending approvals")
    p_list.set_defaults(func=cmd_approvals_list)
    p_decide = approvals_sub.add_parser("decide", help="Approve or reject a pending approval")
    p_decide.add_argument("approval_id")
    p_decide.add_argument("decision", choices=["approved", "rejected"])
    p_decide.set_defaults(func=cmd_approvals_decide)

    p_health = sub.add_parser("healthcheck", help="Verify the database opens and is fully migrated")
    p_health.set_defaults(func=cmd_healthcheck)

    p_heartbeat = sub.add_parser("heartbeat", help="Run one consolidation pass (signals -> initiatives -> goals)")
    p_heartbeat.add_argument("--daily-quota", type=int, default=3, help="Max auto-accepted memory.consolidate actions per day")
    p_heartbeat.set_defaults(func=cmd_heartbeat)

    p_kill = sub.add_parser("kill", help="Stop running job process trees (no-op until Faza C)")
    p_kill.set_defaults(func=cmd_kill)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
