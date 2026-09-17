"""Restore from an encrypted backup produced by recovery.backup.

Decryption needs the age identity (private key) matching the recipient
the backup was encrypted for -- the one secret in this flow, kept in a
password manager / keyring per docs/05-recovery.md, never in this repo.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

from recovery.backup import ensure_age_available


class RestoreError(RuntimeError):
    pass


def restore_backup(
    archive_path: str | Path,
    manifest_path: str | Path,
    identity_path: str | Path,
    dest_dir: str | Path,
) -> Path:
    """Decrypt an archive, verify every file against its manifest checksum,
    and extract into dest_dir. Returns the path to the restored jarvis.db.

    Raises RestoreError if decryption fails or any checksum doesn't match --
    a mismatch means the backup is corrupted or was tampered with, and must
    not be treated as restorable.
    """

    ensure_age_available()
    archive_path = Path(archive_path)
    manifest_path = Path(manifest_path)
    identity_path = Path(identity_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    result = subprocess.run(
        ["age", "-d", "-i", str(identity_path), str(archive_path)],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RestoreError(f"age decryption failed: {result.stderr.decode(errors='replace')}")
    tar_data = result.stdout

    actual_archive_hash = hashlib.sha256(tar_data).hexdigest()
    if actual_archive_hash != manifest["archive_sha256"]:
        raise RestoreError(
            f"archive checksum mismatch: manifest says {manifest['archive_sha256']}, "
            f"got {actual_archive_hash}. The backup may be corrupted or tampered with."
        )

    with tarfile.open(fileobj=io.BytesIO(tar_data), mode="r:gz") as tar:
        tar.extractall(dest_dir, filter="data")

    for file_meta in manifest["files"]:
        extracted = dest_dir / file_meta["path"]
        if not extracted.exists():
            raise RestoreError(f"manifest lists {file_meta['path']!r} but it is missing from the archive")
        actual_hash = hashlib.sha256(extracted.read_bytes()).hexdigest()
        if actual_hash != file_meta["sha256"]:
            raise RestoreError(f"checksum mismatch for {file_meta['path']!r}")

    return dest_dir / "jarvis.db"
