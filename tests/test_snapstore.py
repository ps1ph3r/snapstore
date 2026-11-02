import tempfile
from pathlib import Path

from snapstore.cli import cmd_delete, cmd_init, cmd_snapshot, cmd_status
from snapstore.diff import diff_snapshots
from snapstore.hasher import hash_content, hash_file
from snapstore.models import Repository
from snapstore.object_store import ObjectStore
from snapstore.restore import restore
from snapstore.scanner import scan_directory
from snapstore.snapshot import create_snapshot, delete_snapshot, list_snapshots
from snapstore.status import compute_status


def test_01_hasher_deterministic():
    """Identical content produces identical SHA-256 hash."""
    h1 = hash_content(b"hello world\n")
    h2 = hash_content(b"hello world\n")
    assert h1 == h2
    assert len(h1) == 64


def test_02_object_store_deduplication():
    """Identical file content is stored only once."""
    with tempfile.TemporaryDirectory() as tmp:
        store = ObjectStore(Path(tmp) / "objects")
        content = b"sample document"
        digest = hash_content(content)

        assert store.put(digest, content) is True   # First write stores blob
        assert store.put(digest, content) is False  # Second write deduplicates
        assert store.read(digest) == content


def test_03_scanner_skips_snapstore():
    """Scanner finds files recursively and ignores the .snapstore repository."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "doc.txt").write_text("user file")
        (root / ".snapstore").mkdir()
        (root / ".snapstore" / "internal.txt").write_text("internal")

        scan = scan_directory(root).unwrap()
        assert Path("doc.txt") in scan.paths
        assert Path(".snapstore/internal.txt") not in scan.paths


def test_04_create_snapshot():
    """Snapshot records relative paths mapped to their SHA-256 hashes."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp))
        repo.objects_dir.mkdir(parents=True)
        repo.snapshots_dir.mkdir(parents=True)

        (repo.root / "hello.txt").write_text("hello world")

        manifest = create_snapshot(repo).unwrap()
        assert len(manifest.snapshot_id) == 8
        assert "hello.txt" in manifest.files
        assert manifest.files["hello.txt"] == hash_file(repo.root / "hello.txt")


def test_05_list_snapshots():
    """Listing snapshots returns all snapshots sorted newest first."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp))
        repo.objects_dir.mkdir(parents=True)
        repo.snapshots_dir.mkdir(parents=True)

        (repo.root / "a.txt").write_text("v1")
        s1 = create_snapshot(repo).unwrap()

        (repo.root / "a.txt").write_text("v2")
        s2 = create_snapshot(repo).unwrap()

        snapshots = list_snapshots(repo)
        assert len(snapshots) == 2
        assert snapshots[0].snapshot_id == s2.snapshot_id
        assert snapshots[1].snapshot_id == s1.snapshot_id


def test_06_status_detects_changes():
    """Status classifies Added, Modified, and Deleted files relative to snapshot."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp))
        repo.objects_dir.mkdir(parents=True)
        repo.snapshots_dir.mkdir(parents=True)

        (repo.root / "keep.txt").write_text("original")
        (repo.root / "modify.txt").write_text("v1")
        (repo.root / "delete.txt").write_text("bye")
        create_snapshot(repo).unwrap()

        # Apply changes
        (repo.root / "modify.txt").write_text("v2")
        (repo.root / "delete.txt").unlink()
        (repo.root / "added.txt").write_text("new")

        status = compute_status(repo).unwrap()
        assert status.added == ["added.txt"]
        assert status.modified == ["modify.txt"]
        assert status.deleted == ["delete.txt"]
        assert status.unchanged == ["keep.txt"]


def test_07_diff_snapshots():
    """Diffing two snapshots classifies changes between them."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp))
        repo.objects_dir.mkdir(parents=True)
        repo.snapshots_dir.mkdir(parents=True)

        (repo.root / "f1.txt").write_text("initial")
        s1 = create_snapshot(repo).unwrap()

        (repo.root / "f1.txt").write_text("updated")
        (repo.root / "f2.txt").write_text("new file")
        s2 = create_snapshot(repo).unwrap()

        diff = diff_snapshots(s1, s2)
        assert diff.added == ["f2.txt"]
        assert diff.modified == ["f1.txt"]
        assert not diff.deleted


def test_08_restore_full():
    """Full restore reconstructs entire snapshot state at destination."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "source")
        repo.root.mkdir()
        repo.objects_dir.mkdir(parents=True)
        repo.snapshots_dir.mkdir(parents=True)

        (repo.root / "notes.txt").write_text("important data")
        snap = create_snapshot(repo).unwrap()

        dest = Path(tmp) / "restored"
        res = restore(repo, snap.snapshot_id, dest)
        assert res.is_ok()
        assert (dest / "notes.txt").read_text() == "important data"


def test_09_restore_selective():
    """Selective restore copies only specified file paths."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repository(Path(tmp) / "source")
        repo.root.mkdir()
        repo.objects_dir.mkdir(parents=True)
        repo.snapshots_dir.mkdir(parents=True)

        (repo.root / "keep.txt").write_text("keep me")
        (repo.root / "skip.txt").write_text("skip me")
        snap = create_snapshot(repo).unwrap()

        dest = Path(tmp) / "restored"
        res = restore(repo, snap.snapshot_id, dest, files=["keep.txt"])
        assert res.is_ok()
        assert (dest / "keep.txt").exists()
        assert not (dest / "skip.txt").exists()


def test_10_cli_smoke_workflow():
    """Smoke test running high-level CLI commands directly."""
    import argparse

    with tempfile.TemporaryDirectory() as tmp:
        root_str = str(Path(tmp) / "repo")

        # 1. init
        assert cmd_init(argparse.Namespace(directory=root_str)).is_ok()

        # 2. snapshot
        (Path(root_str) / "file.txt").write_text("content")
        assert cmd_snapshot(argparse.Namespace(directory=root_str)).is_ok()

        # 3. status
        status_res = cmd_status(argparse.Namespace(directory=root_str, long=False))
        assert status_res.is_ok()
        assert status_res.unwrap() == "No changes"

        # 4. snapshot when clean is blocked
        clean_snap = cmd_snapshot(argparse.Namespace(directory=root_str, allow_empty=False))
        assert clean_snap.is_err()
        assert "clean" in clean_snap.error

        # 5. delete snapshot
        repo = Repository(Path(root_str))
        snap_id = repo.get_head()
        assert snap_id is not None
        del_res = cmd_delete(argparse.Namespace(directory=root_str, snapshot_id=snap_id))
        assert del_res.is_ok()
        assert repo.get_head() is None
