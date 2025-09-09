"""Symlink management utilities."""

import os
import shutil
from pathlib import Path


def supports_symlinks() -> bool:
    """Check if the current system supports symlinks."""
    return hasattr(os, 'symlink')


def create_symlink(source: Path, target: Path, *, force: bool = False) -> bool:
    """Create a symlink from target to source.

    Returns True if symlink was created, False if fallback copy was used.
    """
    if target.exists() and not force:
        msg = f'Target already exists: {target}'
        raise FileExistsError(msg)

    if target.exists() and force:
        remove_target(target)

    if not source.exists():
        msg = f'Source does not exist: {source}'
        raise FileNotFoundError(msg)

    if supports_symlinks():
        target.symlink_to(source, target_is_directory=source.is_dir())
        return True

    # Fallback to copying
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)
    return False


def remove_target(target: Path) -> None:
    """Remove a target file or directory (symlink or copy)."""
    if target.is_symlink():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)
    elif target.is_file():
        target.unlink()


def is_managed_link(target: Path) -> bool:
    """Check if a path appears to be a pkglink-managed symlink."""
    return target.name.startswith('.') and (target.is_symlink() or target.is_dir())


def list_managed_links(directory: Path | None = None) -> list[Path]:
    """List all potential pkglink-managed links in a directory."""
    if directory is None:
        directory = Path.cwd()

    return [item for item in directory.iterdir() if is_managed_link(item)]
