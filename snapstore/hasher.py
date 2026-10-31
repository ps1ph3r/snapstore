import hashlib
from pathlib import Path

CHUNK_SIZE = 65536


def hash_file(filepath: Path) -> str:
    """Compute SHA-256 digest of a file using chunked streaming."""
    sha = hashlib.sha256()
    with filepath.open("rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            sha.update(chunk)
    return sha.hexdigest()


def hash_content(content: bytes) -> str:
    """Compute SHA-256 digest of raw byte content."""
    return hashlib.sha256(content).hexdigest()
