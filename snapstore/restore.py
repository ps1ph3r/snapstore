import shutil
from pathlib import Path

from .models import Repository, SnapshotManifest
from .object_store import ObjectStore
from .result import Err, Ok, Result
from .snapshot import get_snapshot_by_id


def _restore_files(
    snapshot: SnapshotManifest,
    store: ObjectStore,
    dest_root: Path,
    requested_files: list[str] | None = None) -> Result[int, str]:
    targets = requested_files if requested_files is not None else list(snapshot.files.keys())
    missing = [f for f in targets if f not in snapshot.files]
    if missing:
        return Err(f"Files not found in snapshot: {missing}")

    dest_root.mkdir(parents=True, exist_ok=True)
    for rel_path in targets:
        dest_path = (dest_root / rel_path).resolve()
        if not dest_path.is_relative_to(dest_root):
            return Err(f"Unsafe path traversal detected: {rel_path}")

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(store.get_path(snapshot.files[rel_path]), dest_path)

    return Ok(len(targets))


def restore(
    repo: Repository,
    snapshot_id: str,
    destination: Path | str,
    files: list[str] | None = None,
) -> Result[int, str]:
    """Restore entire snapshot or selective file paths from a Repository."""
    dest_root = Path(destination).resolve()
    return (
        get_snapshot_by_id(repo.snapshots_dir, snapshot_id)
        .and_then(lambda snap: _restore_files(snap, repo.object_store, dest_root, files))
    )


def restore_snapshot(
    snapshots_dir: Path,
    objects_dir: Path,
    snapshot_id: str,
    destination: Path | str,
    files: list[str] | None = None
) -> Result[int, str]:
    """Restore entire snapshot or selective file paths using monadic chain."""
    store = ObjectStore(objects_dir)
    dest_root = Path(destination).resolve()

    return (
        get_snapshot_by_id(snapshots_dir, snapshot_id)
        .and_then(lambda snap: _restore_files(snap, store, dest_root, files))
    )
