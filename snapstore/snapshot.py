import time
import uuid
from pathlib import Path

from .hasher import hash_file
from .models import Repository, ScanResult, SnapshotManifest
from .object_store import ObjectStore
from .result import Err, Result, attempt
from .scanner import scan_directory


def _store_scanned_files(scan: ScanResult, target_dir: Path, object_store: ObjectStore) -> dict[str, str]:
    files: dict[str, str] = {}
    for rel_path in scan.relative_paths:
        file_path = target_dir / rel_path
        digest = hash_file(file_path)
        object_store.put(digest, file_path.read_bytes())
        files[str(rel_path)] = digest
    return files


def create_snapshot(repo: Repository) -> Result[SnapshotManifest, str]:
    """Create a new snapshot in the repository and advance HEAD."""
    return (
        create_snapshot_manifest(repo.root, repo.object_store, parent_id=repo.get_head())
        .and_then(lambda m: save_snapshot_manifest(m, repo.snapshots_dir).map(lambda _: m))
        .map(lambda m: (repo.set_head(m.snapshot_id), m)[1])
    )


def create_snapshot_manifest(
    target_dir: Path | str,
    object_store: ObjectStore,
    parent_id: str | None = None) -> Result[SnapshotManifest, str]:
    """Create a new snapshot manifest by chaining directory scan and blob storage."""
    target_path = Path(target_dir)
    return (
        scan_directory(target_path)
        .map(lambda scan: _store_scanned_files(scan, target_path, object_store))
        .map(lambda files: SnapshotManifest(
            snapshot_id=uuid.uuid4().hex[:8],
            timestamp=time.time(),
            files=files,
            parent_id=parent_id
        ))
    )


def save_snapshot_manifest(manifest: SnapshotManifest, snapshots_dir: Path) -> Result[Path, str]:
    """Persist snapshot manifest to JSON file."""
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = snapshots_dir / f"{manifest.snapshot_id}.json"
    return attempt(lambda: manifest_file.write_text(manifest.to_json())).map(lambda _: manifest_file)


def list_snapshots(target: Repository | Path) -> list[SnapshotManifest]:
    """List all snapshots sorted newest first."""
    snapshots_dir = target.snapshots_dir if isinstance(target, Repository) else Path(target)
    manifests = [
        SnapshotManifest.from_json(f.read_text())
        for f in snapshots_dir.glob("*.json")
    ]
    return sorted(manifests, key=lambda m: m.timestamp, reverse=True)


def get_latest_snapshot(target: Repository | Path) -> SnapshotManifest | None:
    """Retrieve the most recent snapshot manifest."""
    snapshots = list_snapshots(target)
    return snapshots[0] if snapshots else None


def get_snapshot_by_id(target: Repository | Path, snapshot_id: str) -> Result[SnapshotManifest, str]:
    """Find a snapshot by exact or prefix ID match."""
    snapshots_dir = target.snapshots_dir if isinstance(target, Repository) else Path(target)
    for file in snapshots_dir.glob("*.json"):
        if file.stem.startswith(snapshot_id):
            return attempt(lambda: SnapshotManifest.from_json(file.read_text()))
    return Err(f"Snapshot '{snapshot_id}' not found")


def get_head(snapstore_dir: Path) -> str | None:
    """Read current HEAD snapshot ID."""
    head_file = snapstore_dir / "HEAD"
    if head_file.exists():
        content = head_file.read_text().strip()
        return content if content else None
    return None


def set_head(snapstore_dir: Path, snapshot_id: str) -> None:
    """Update current HEAD pointer to snapshot ID."""
    (snapstore_dir / "HEAD").write_text(f"{snapshot_id.strip()}\n")


def get_history(target: Repository | Path, from_id: str | None = None) -> list[SnapshotManifest]:
    """Walk snapshot history backward following parent links."""
    snapshots_dir = target.snapshots_dir if isinstance(target, Repository) else Path(target)
    start_id = from_id or (target.get_head() if isinstance(target, Repository) else get_head(snapshots_dir.parent))
    current = (
        get_snapshot_by_id(snapshots_dir, start_id).unwrap_or(None)
        if start_id
        else get_latest_snapshot(snapshots_dir)
    )

    history: list[SnapshotManifest] = []
    while current:
        history.append(current)
        if not current.parent_id:
            break
        parent_res = get_snapshot_by_id(snapshots_dir, current.parent_id)
        current = parent_res.unwrap() if parent_res.is_ok() else None

    return history
