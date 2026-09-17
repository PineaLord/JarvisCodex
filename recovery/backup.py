"""Encrypted backup, built on age (https://age-encryption.org).

Per docs/05-recovery.md: the ledger, exports and config get encrypted; the
manifest and checksums are not secret and stay in the clear next to the
encrypted archive, so a backup can be identified and integrity-checked
without decrypting it.

Encryption is asymmetric (`age -r <recipient>`): creating a backup only
ever needs a public recipient key, never a private key. The private
identity that can decrypt backups is the one artifact that must live in a
password manager / keyring, never in this repository -- generate it once
with `age-keygen` and see docs/05-recovery.md for the exact procedure.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from storage.export import export_state

SCHEMA_VERSION = 1


class BackupError(RuntimeError):
    pass


def ensure_age_available() -> None:
    if shutil.which("age") is None:
        raise BackupError(
            "age is not installed. Install it (e.g. `omarchy pkg add age`) "
            "before creating or restoring encrypted backups."
        )


@dataclass(frozen=True)
class BackupManifest:
    schema_version: int
    created_at: str
    event_count: int
    files: list
    archive_sha256: str

    def to_dict(self) -> dict:
        return asdict(self)


def _stage_snapshot(db_path: Path, staging_dir: Path) -> int:
    """Copy a consistent snapshot of the live database and export its
    projections into staging_dir. Returns the event count at snapshot time."""

    snapshot_db = staging_dir / "jarvis.db"
    source = sqlite3.connect(db_path)
    dest = sqlite3.connect(snapshot_db)
    try:
        with dest:
            source.backup(dest)  # sqlite3's own snapshot API: safe even if db is in use
        event_count = dest.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        export_state(dest, staging_dir / "export")
    finally:
        source.close()
        dest.close()
    return event_count


def _tar_staging_dir(staging_dir: Path) -> tuple[bytes, list[dict]]:
    files_meta = []
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in sorted(staging_dir.rglob("*")):
            if not path.is_file():
                continue
            data = path.read_bytes()
            rel = str(path.relative_to(staging_dir))
            files_meta.append({
                "path": rel,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            })
            tar.add(path, arcname=rel)
    return buf.getvalue(), files_meta


def create_backup(db_path: str | Path, out_dir: str | Path, recipient: str) -> tuple[Path, Path]:
    """Create an encrypted, integrity-checked backup of db_path into out_dir.

    Writes two files: `jarvis-<timestamp>.tar.gz.age` (encrypted ledger +
    export) and `jarvis-<timestamp>.manifest.json` (unencrypted checksums,
    event count, schema version). Returns (archive_path, manifest_path).
    """

    ensure_age_available()
    db_path = Path(db_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        event_count = _stage_snapshot(db_path, staging)
        tar_data, files_meta = _tar_staging_dir(staging)

    archive_hash = hashlib.sha256(tar_data).hexdigest()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = out_dir / f"jarvis-{timestamp}.tar.gz.age"
    manifest_path = out_dir / f"jarvis-{timestamp}.manifest.json"

    result = subprocess.run(
        ["age", "-r", recipient, "-o", str(archive_path)],
        input=tar_data,
        capture_output=True,
    )
    if result.returncode != 0:
        raise BackupError(f"age encryption failed: {result.stderr.decode(errors='replace')}")

    manifest = BackupManifest(
        schema_version=SCHEMA_VERSION,
        created_at=timestamp,
        event_count=event_count,
        files=files_meta,
        archive_sha256=archive_hash,
    )
    manifest_path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    return archive_path, manifest_path
