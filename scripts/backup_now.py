#!/usr/bin/env python3
"""Create one encrypted backup of the live ledger.

Usage:
    JARVIS_CODEX_DATA_DIR=/path/to/data/live \
    JARVIS_CODEX_BACKUP_RECIPIENT=age1... \
    python3 scripts/backup_now.py [backup_out_dir]

The recipient is a public age key, not a secret -- see docs/05-recovery.md
for how to generate one and where the matching private identity belongs
(a password manager / keyring, never this repo).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recovery.backup import BackupError, create_backup  # noqa: E402


def main() -> int:
    data_dir = os.environ.get("JARVIS_CODEX_DATA_DIR")
    recipient = os.environ.get("JARVIS_CODEX_BACKUP_RECIPIENT")

    if not data_dir or not recipient:
        print(
            "Set JARVIS_CODEX_DATA_DIR and JARVIS_CODEX_BACKUP_RECIPIENT "
            "(see .env.example and docs/05-recovery.md).",
            file=sys.stderr,
        )
        return 2

    db_path = Path(data_dir) / "jarvis.db"
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(data_dir).parent / "backups"

    try:
        archive_path, manifest_path = create_backup(db_path, out_dir, recipient)
    except BackupError as e:
        print(f"Backup failed: {e}", file=sys.stderr)
        return 1

    print(f"Backup written: {archive_path}")
    print(f"Manifest:       {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
