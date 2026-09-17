#!/usr/bin/env python3
"""Restore an encrypted backup into a clean directory.

Usage:
    python3 scripts/restore_backup.py <archive.tar.gz.age> <manifest.json> \
        <identity.txt> <dest_dir>

<identity.txt> is the private age identity -- pull it from your password
manager / keyring for this, never commit it. See docs/05-recovery.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recovery.restore import RestoreError, restore_backup  # noqa: E402


def main() -> int:
    if len(sys.argv) != 5:
        print(__doc__, file=sys.stderr)
        return 2

    archive_path, manifest_path, identity_path, dest_dir = (Path(a) for a in sys.argv[1:5])

    try:
        restored_db = restore_backup(archive_path, manifest_path, identity_path, dest_dir)
    except RestoreError as e:
        print(f"Restore failed: {e}", file=sys.stderr)
        return 1

    print(f"Restored database: {restored_db}")
    print("Next: open it, run storage.migrate.migrate() (no-op if already current), "
          "then storage.projections.rebuild_projections() to verify state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
