import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .object_store import ObjectStore
from .result import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class Repository:
    """Represents a local SnapStore repository."""
    root: Path

    @property
    def snapstore_dir(self) -> Path:
        return self.root / ".snapstore"

    @property
    def objects_dir(self) -> Path:
        return self.snapstore_dir / "objects"

    @property
    def snapshots_dir(self) -> Path:
        return self.snapstore_dir / "snapshots"

    @property
    def head_file(self) -> Path:
        return self.snapstore_dir / "HEAD"

    @property
    def object_store(self) -> ObjectStore:
        return ObjectStore(self.objects_dir)

    def is_initialized(self) -> bool:
        return self.snapstore_dir.is_dir()

    def get_head(self) -> str | None:
        """Read current HEAD snapshot ID."""
        if self.head_file.exists():
            content = self.head_file.read_text().strip()
            return content if content else None
        return None

    def set_head(self, snapshot_id: str) -> None:
        """Update current HEAD pointer to snapshot ID."""
        self.head_file.write_text(f"{snapshot_id.strip()}\n")


def open_repo(directory: str | Path = ".") -> Result[Repository, str]:
    """Resolve and validate a SnapStore repository directory."""
    repo = Repository(Path(directory).resolve())
    if not repo.is_initialized():
        return Err("Not a SnapStore directory. Run 'snapstore init' first.")
    return Ok(repo)


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Result of scanning a directory tree."""
    root: Path
    paths: list[Path]

    @property
    def relative_paths(self) -> list[Path]:
        return self.paths


@dataclass(frozen=True, slots=True)
class SnapshotManifest:
    """Manifest representing directory state at a point in time."""
    snapshot_id: str
    timestamp: float
    files: dict[str, str]
    parent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.snapshot_id,
            "timestamp": self.timestamp,
            "files": self.files,
        }
        if self.parent_id is not None:
            data["parent_id"] = self.parent_id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SnapshotManifest":
        return cls(
            snapshot_id=data["id"],
            timestamp=data["timestamp"],
            files=data["files"],
            parent_id=data.get("parent_id"),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "SnapshotManifest":
        return cls.from_dict(json.loads(json_str))


@dataclass(frozen=True, slots=True)
class DiffResult:
    """Classified file differences between two snapshot states or working tree."""
    added: list[str]
    modified: list[str]
    deleted: list[str]
    unchanged: list[str]

    def __bool__(self) -> bool:
        return bool(self.added or self.modified or self.deleted)

    def __iter__(self):
        """Enable tuple unpacking: added, modified, deleted, unchanged = diff."""
        return iter((self.added, self.modified, self.deleted, self.unchanged))

    def short_format(self) -> str:
        """Render jj-style short status output (A/M/D)."""
        lines = (
            [f"A  {p}" for p in sorted(self.added)]
            + [f"M  {p}" for p in sorted(self.modified)]
            + [f"D  {p}" for p in sorted(self.deleted)]
        )
        return "\n".join(lines) if lines else "No changes"

    def long_format(self) -> str:
        """Render diff section summary output."""
        sections: list[str] = []
        for name, paths in [
            ("ADDED", self.added),
            ("MODIFIED", self.modified),
            ("DELETED", self.deleted),
            ("UNCHANGED", self.unchanged),
        ]:
            if paths:
                sections.append(f"{name}\n" + "\n".join(f"    {p}" for p in sorted(paths)))
        return "\n\n".join(sections) if sections else "No changes"
