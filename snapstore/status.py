from pathlib import Path

from .diff import diff_mappings
from .hasher import hash_file
from .models import DiffResult, Repository
from .result import Result
from .scanner import scan_directory
from .snapshot import get_latest_snapshot


def compute_status(target: Repository | Path | str, snapshots_dir: Path | None = None) -> Result[DiffResult, str]:
    """Compare working tree against latest snapshot manifest via set algebra."""
    if isinstance(target, Repository):
        root = target.root
        s_dir = target.snapshots_dir
    else:
        root = Path(target)
        s_dir = snapshots_dir or (root / ".snapstore" / "snapshots")

    latest = get_latest_snapshot(s_dir)
    base_files = latest.files if latest else {}

    return scan_directory(root).map(
        lambda scan: diff_mappings(
            base_files,
            {str(p): hash_file(root / p) for p in scan.paths},
        )
    )
