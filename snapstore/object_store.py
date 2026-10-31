from pathlib import Path


class ObjectStore:
    """Content-addressed immutable blob store."""

    def __init__(self, objects_dir: Path | str):
        self.objects_dir = Path(objects_dir)
        self.objects_dir.mkdir(parents=True, exist_ok=True)

    def _object_path(self, content_hash: str) -> Path:
        """Resolve content hash to two-character sharded path."""
        return self.objects_dir / content_hash[:2] / content_hash[2:]

    def exists(self, content_hash: str) -> bool:
        """Check whether an object exists in the store."""
        return self._object_path(content_hash).exists()

    def get_path(self, content_hash: str) -> Path:
        """Get filesystem path for an object by its hash."""
        return self._object_path(content_hash)

    def read(self, content_hash: str) -> bytes:
        """Read raw content bytes for an object by its hash."""
        return self._object_path(content_hash).read_bytes()

    def put(self, content_hash: str, content: bytes) -> bool:
        """Store content blob if not already present. Returns True if written."""
        path = self._object_path(content_hash)
        if path.exists():
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return True
