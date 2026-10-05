"""Atomic JSON storage. Backups contain only the last validated document."""
import json
import os
import tempfile
import threading
from pathlib import Path

_lock = threading.RLock()


def atomic_bytes(path: Path, payload: bytes):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def write_json(path, value, *, backup=True):
    path = Path(path)
    payload = json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str).encode('utf8')
    with _lock:
        if backup and path.exists():
            try:
                old = path.read_bytes()
                json.loads(old)
            except (OSError, ValueError):
                pass
            else:
                atomic_bytes(path.with_suffix(path.suffix + '.bak'), old)
        atomic_bytes(path, payload)


def read_json(path, default=None, *, validate=None):
    """Return (value, recovery message), trying the last-good file if necessary."""
    path = Path(path)
    with _lock:
        for candidate in (path, path.with_suffix(path.suffix + '.bak')):
            try:
                value = json.loads(candidate.read_text('utf8'))
                if validate:
                    validate(value)
                return value, ("Recovered the last saved copy after an interrupted write." if candidate != path else "")
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                continue
    message = "Saved data could not be read. Sign in to refresh it." if path.exists() else ""
    return default, message


def validate_snapshot(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid snapshot')
    for name in ('courses', 'assignments', 'grades', 'deadlines', 'content_nodes', 'announcements'):
        rows = value.get(name, [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError('Invalid snapshot collection')


def remove_json(path):
    with _lock:
        Path(path).unlink(missing_ok=True)
        Path(path).with_suffix(Path(path).suffix + '.bak').unlink(missing_ok=True)
