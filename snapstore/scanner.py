import os
from pathlib import Path

from .models import ScanResult
from .result import Err, Ok, Result


def scan_directory(root: Path | str, exclude_dirs: set[str] | None = None) -> Result[ScanResult, str]:
    """Recursively scan directory, returning relative file paths."""
    ignored = exclude_dirs or {".snapstore"}
    root_path = Path(root)

    if not root_path.is_dir():
        return Err(f"Directory does not exist: {root_path}")

    paths: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in ignored]
        base = Path(dirpath).relative_to(root_path)
        for filename in filenames:
            paths.append(base / filename if base != Path(".") else Path(filename))

    paths.sort()
    return Ok(ScanResult(root=root_path, paths=paths))
