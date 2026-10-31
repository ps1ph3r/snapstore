import difflib
from pathlib import Path

from .hasher import hash_file
from .models import DiffResult, SnapshotManifest
from .object_store import ObjectStore
from .result import attempt
from .scanner import scan_directory


def diff_mappings(
    from_files: dict[str, str],
    to_files: dict[str, str],
) -> DiffResult:
    """Compare two path-to-hash mappings using set algebra."""
    from_paths = set(from_files.keys())
    to_paths = set(to_files.keys())

    added = sorted(to_paths - from_paths)
    deleted = sorted(from_paths - to_paths)
    common = from_paths & to_paths

    modified = sorted(p for p in common if from_files[p] != to_files[p])
    unchanged = sorted(p for p in common if from_files[p] == to_files[p])

    return DiffResult(added, modified, deleted, unchanged)


def diff_snapshots(
    from_snap: SnapshotManifest,
    to_snap: SnapshotManifest,
) -> DiffResult:
    """Compare two snapshots and classify file changes."""
    return diff_mappings(from_snap.files, to_snap.files)


def format_status_result(
    added: list[str],
    modified: list[str],
    deleted: list[str],
    unchanged: list[str],
) -> str:
    """Format status changes with jj-style prefixes (A/M/D)."""
    return DiffResult(added, modified, deleted, unchanged).short_format()


def format_diff_sections(
    added: list[str],
    modified: list[str],
    deleted: list[str],
    unchanged: list[str],
) -> str:
    """Format diff changes into labeled sections."""
    return DiffResult(added, modified, deleted, unchanged).long_format()


def _is_binary(content: bytes) -> bool:
    """Determine if a byte sequence represents binary data."""
    return b"\x00" in content or attempt(lambda: content.decode("utf-8")).is_err()


def diff_content(old_content: bytes, new_content: bytes, context_lines: int = 3) -> list[str]:
    """Generate unified diff lines between byte contents."""
    if _is_binary(old_content) or _is_binary(new_content):
        return ["Binary file changed"]

    diff = difflib.unified_diff(
        old_content.decode("utf-8", errors="replace").splitlines(keepends=True),
        new_content.decode("utf-8", errors="replace").splitlines(keepends=True),
        fromfile="snapshot",
        tofile="current",
        lterm="",
        n=context_lines,
    )
    return list(diff)


def diff_snapshot_vs_current(
    snapshot: SnapshotManifest,
    target_dir: Path,
    objects: ObjectStore | Path,
) -> list[str]:
    """Compare a snapshot against the working directory and return git-style diffs."""
    store = objects if isinstance(objects, ObjectStore) else ObjectStore(objects)
    scan_res = scan_directory(target_dir)
    if scan_res.is_err():
        return [f"Error: {scan_res.error}"]
    scan_result = scan_res.unwrap()

    current_hashes = {str(p): hash_file(target_dir / p) for p in scan_result.relative_paths}

    added, modified, deleted, _ = diff_mappings(snapshot.files, current_hashes)
    all_changed = sorted(added + modified + deleted)
    if not all_changed:
        return ["No changes"]

    output: list[str] = []

    for path in all_changed:
        if path in added:
            output.append(f"--- /dev/null")
            output.append(f"+++ b/{path}")
            content = (target_dir / path).read_bytes()
            output.extend(diff_content(b"", content) if not _is_binary(content) else ["Binary file added"])
            output.append("")
        elif path in deleted:
            output.append(f"--- a/{path}")
            output.append("+++ /dev/null")
            output.append("File deleted")
            output.append("")
        elif path in modified:
            output.append(f"--- a/{path}")
            output.append(f"+++ b/{path}")
            old_hash = snapshot.files[path]
            old_content = store.read(old_hash)
            new_content = (target_dir / path).read_bytes()
            output.extend(
                diff_content(old_content, new_content)
                if not _is_binary(old_content) and not _is_binary(new_content)
                else ["Binary files differ"]
            )
            output.append("")

    if output and output[-1] == "":
        output.pop()
    return output if output else ["No changes"]
