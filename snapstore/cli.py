import argparse
import sys
from datetime import datetime
from pathlib import Path

from .diff import diff_snapshot_vs_current, diff_snapshots
from .models import Repository, open_repo
from .restore import restore
from .result import Err, Ok, Result, attempt
from .snapshot import (
    create_snapshot,
    get_history,
    get_latest_snapshot,
    get_snapshot_by_id,
    list_snapshots,
)
from .status import compute_status


def cmd_init(args: argparse.Namespace) -> Result[str, str]:
    """Initialize repository directories."""
    repo = Repository(Path(args.directory).resolve())
    return (
        attempt(lambda: (
            repo.objects_dir.mkdir(parents=True, exist_ok=True),
            repo.snapshots_dir.mkdir(parents=True, exist_ok=True),
        ))
        .map(lambda _: f"Initialized SnapStore in {repo.snapstore_dir}")
        .map_err(lambda err: f"Error initializing SnapStore: {err}")
    )


def cmd_snapshot(args: argparse.Namespace) -> Result[str, str]:
    """Create a new snapshot and advance HEAD."""
    return (
        open_repo(args.directory)
        .and_then(create_snapshot)
        .map(lambda manifest: f"Created snapshot {manifest.snapshot_id}")
    )


def _format_snapshot_list(repo: Repository) -> str:
    snapshots = list_snapshots(repo)
    if not snapshots:
        return "No snapshots found."

    lines = [f"{'ID':<8} {'Timestamp':<20} {'Files':<8}", "-" * 40]
    for s in snapshots:
        ts = datetime.fromtimestamp(s.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"{s.snapshot_id:<8} {ts:<20} {len(s.files):<8}")
    return "\n".join(lines)


def cmd_list(args: argparse.Namespace) -> Result[str, str]:
    """List snapshots in chronological order."""
    return open_repo(args.directory).map(_format_snapshot_list)


def _format_snapshot_log(repo: Repository) -> str:
    history = get_history(repo)
    if not history:
        return "No snapshots found."

    lines = []
    head_id = repo.get_head()
    for i, s in enumerate(history):
        is_head = (s.snapshot_id == head_id)
        marker = "@" if is_head else "○"
        head_tag = " (HEAD)" if is_head else ""
        root_tag = " (root)" if not s.parent_id else ""
        ts = datetime.fromtimestamp(s.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"{marker}  {s.snapshot_id}{head_tag}{root_tag}  {ts}  ({len(s.files)} files)")
        if s.parent_id:
            lines.append(f"│  parent: {s.parent_id}")
        elif i < len(history) - 1:
            lines.append("│")
    return "\n".join(lines)


def cmd_log(args: argparse.Namespace) -> Result[str, str]:
    """Display snapshot lineage history graph."""
    return open_repo(args.directory).map(_format_snapshot_log)


def _run_diff(repo: Repository, args: argparse.Namespace) -> Result[str, str]:
    if args.snapshot1 and args.snapshot2:
        return (
            get_snapshot_by_id(repo, args.snapshot1)
            .and_then(lambda s1: get_snapshot_by_id(repo, args.snapshot2).map(lambda s2: (s1, s2)))
            .map(lambda pair: diff_snapshots(pair[0], pair[1]).long_format())
            .map_err(lambda _: "One or both snapshots not found")
        )

    if args.snapshot1 and args.parent:
        res = get_snapshot_by_id(repo, args.snapshot1)
        match res:
            case Ok(snap) if not snap.parent_id:
                return Ok(f"Snapshot '{args.snapshot1}' is a root snapshot (no parent).")
            case Ok(snap) if snap.parent_id:
                return (
                    get_snapshot_by_id(repo, snap.parent_id)
                    .map(lambda p_snap: diff_snapshots(p_snap, snap).long_format())
                )
            case Err(_) as err:
                return err

    target_snap = (
        get_snapshot_by_id(repo, args.snapshot1).unwrap_or(None)
        if args.snapshot1
        else get_latest_snapshot(repo)
    )

    if not target_snap:
        if args.snapshot1:
            return Err(f"Snapshot '{args.snapshot1}' not found")
        return Ok("No snapshots found. Create one with 'snapstore snapshot'.")

    diff_lines = diff_snapshot_vs_current(target_snap, repo.root, repo.object_store)
    return Ok("\n".join(diff_lines))


def cmd_diff(args: argparse.Namespace) -> Result[str, str]:
    """Diff two snapshots or working tree against a snapshot."""
    return open_repo(args.directory).and_then(lambda repo: _run_diff(repo, args))


def cmd_status(args: argparse.Namespace) -> Result[str, str]:
    """Display status of working tree relative to latest snapshot."""
    return (
        open_repo(args.directory)
        .and_then(compute_status)
        .map(lambda res: res.long_format() if args.long else res.short_format())
    )


def cmd_restore(args: argparse.Namespace) -> Result[str, str]:
    """Restore a snapshot to target destination."""
    dest = Path(args.destination).resolve()
    return open_repo(args.directory).and_then(lambda repo: (
        restore(repo, args.snapshot_id, dest, args.files or None)
        .map(lambda count: (
            repo.set_head(args.snapshot_id) if dest == repo.root and not args.files else None,
            f"Restored {count} file(s) from snapshot {args.snapshot_id} to {dest}" if args.files
            else f"Restored snapshot {args.snapshot_id} to {dest}"
        )[1])
    ))


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to command handler."""
    parser = argparse.ArgumentParser(
        prog="snapstore",
        description="SnapStore - Local snapshot-based backup and recovery system",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Target directory (default: current directory)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    p_init = subparsers.add_parser("init", help="Initialize a directory for snapshots")
    p_init.set_defaults(func=cmd_init)

    p_snapshot = subparsers.add_parser("snapshot", help="Create a snapshot")
    p_snapshot.set_defaults(func=cmd_snapshot)

    p_list = subparsers.add_parser("list", help="List all snapshots")
    p_list.set_defaults(func=cmd_list)

    p_log = subparsers.add_parser("log", help="Display snapshot lineage history graph")
    p_log.set_defaults(func=cmd_log)

    p_diff = subparsers.add_parser("diff", help="Diff snapshots or current vs snapshot")
    p_diff.add_argument("snapshot1", nargs="?", help="First snapshot ID (or omit for current vs latest)")
    p_diff.add_argument("snapshot2", nargs="?", help="Second snapshot ID (for snapshot-snapshot diff)")
    p_diff.add_argument("--parent", "-p", action="store_true", help="Diff snapshot against its parent")
    p_diff.set_defaults(func=cmd_diff)

    p_status = subparsers.add_parser("status", help="Show current directory status vs latest snapshot")
    p_status.add_argument("--long", "-l", action="store_true", help="Long format with sections")
    p_status.set_defaults(func=cmd_status)

    p_restore = subparsers.add_parser("restore", help="Restore a snapshot")
    p_restore.add_argument("snapshot_id", help="Snapshot ID to restore")
    p_restore.add_argument("destination", help="Destination directory")
    p_restore.add_argument("files", nargs="*", help="Specific files to restore (omit for all)")
    p_restore.set_defaults(func=cmd_restore)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1

    result: Result[str, str] = args.func(args)
    match result:
        case Ok(message):
            if message:
                print(message)
            return 0
        case Err(err):
            print(f"Error: {err}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
