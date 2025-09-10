"""Symlink management utilities."""

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def supports_symlinks() -> bool:
    """Check if the current system supports symlinks."""
    return hasattr(os, 'symlink')


def create_symlink(source: Path, target: Path, *, force: bool = False) -> bool:
    """Create a symlink from target to source.

    Returns True if symlink was created, False if fallback copy was used.
    """
    logger.info('Creating symlink: %s -> %s (force=%s)', target, source, force)

    if target.exists() and not force:
        logger.error('Target already exists and force=False: %s', target)
        msg = f'Target already exists: {target}'
        raise FileExistsError(msg)

    if target.exists() and force:
        logger.info('Removing existing target: %s', target)
        remove_target(target)

    if not source.exists():
        logger.error('Source does not exist: %s', source)
        msg = f'Source does not exist: {source}'
        raise FileNotFoundError(msg)

    if supports_symlinks():
        logger.info('Creating symlink using os.symlink')
        target.symlink_to(source, target_is_directory=source.is_dir())
        logger.info('Successfully created symlink')
        return True

    # Fallback to copying
    logger.info('Symlinks not supported, falling back to copy')
    if source.is_dir():
        logger.info('Copying directory tree')
        shutil.copytree(source, target)
    else:
        logger.info('Copying file')
        shutil.copy2(source, target)
    logger.info('Successfully created copy')
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
