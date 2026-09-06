from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import TextIO


def ensure_private_directory(path: Path) -> None:
    """Create an owner-only directory and reject unsafe existing objects."""
    if path.is_symlink():
        raise OSError(f"Refusing symlinked private directory: {path}")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode):
        raise NotADirectoryError(path)
    _require_current_owner(path, info.st_uid)
    if os.name == "posix":
        path.chmod(0o700, follow_symlinks=False)


def ensure_private_file(path: Path) -> None:
    """Create or harden an owner-only regular file without following symlinks."""
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(f"Refusing non-regular private file: {path}")
        _require_current_owner(path, info.st_uid)
        if os.name == "posix":
            os.fchmod(fd, 0o600)
    finally:
        os.close(fd)


def open_private_text(path: Path) -> TextIO:
    """Open a regular text file for replacement with mode 0600."""
    if path.is_symlink():
        raise OSError(f"Refusing symlinked output file: {path}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(f"Refusing non-regular output file: {path}")
        _require_current_owner(path, info.st_uid)
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        return os.fdopen(fd, "w", encoding="utf-8")
    except Exception:
        os.close(fd)
        raise


def harden_existing_file(path: Path) -> None:
    """Apply owner-only mode to an existing regular file."""
    if path.exists():
        ensure_private_file(path)


def _require_current_owner(path: Path, owner: int) -> None:
    getuid = getattr(os, "getuid", None)
    if getuid is not None and owner != getuid():
        raise PermissionError(f"Private path is not owned by the current user: {path}")
