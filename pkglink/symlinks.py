"""Symlink management utilities."""

import os
import shutil
from pathlib import Path

from pkglink.logging import get_logger

logger = get_logger(__name__)


def supports_symlinks() -> bool:
    """Check if the current system supports symlinks."""
    return hasattr(os, 'symlink')


def create_symlink(source: Path, target: Path, *, force: bool = False) -> bool:
    """Create a symlink from target to source.

    Returns True if symlink was created, False if fallback copy was used.
    """
    logger.info(
        'creating_symlink',
        target=str(target),
        source=str(source),
        _verbose_force=force,
    )

    if target.exists():
        if force:
            logger.info('removing_existing_target', target=str(target))
            remove_target(target)
        else:
            logger.error('target_already_exists', target=str(target))
            msg = f'Target already exists: {target}'
            raise FileExistsError(msg)

    if not source.exists():
        logger.error('source_does_not_exist', source=str(source))
        msg = f'Source does not exist: {source}'
        raise FileNotFoundError(msg)

    if supports_symlinks():
        logger.debug('creating_symlink_using_os_symlink')
        target.symlink_to(source, target_is_directory=source.is_dir())
        logger.info('symlink_created_successfully')
        return True

    # Fallback to copying
    logger.debug('symlinks_not_supported_falling_back_to_copy')
    if source.is_dir():
        logger.debug('copying_directory_tree')
        shutil.copytree(source, target)
    else:
        logger.debug('copying_file')
        shutil.copy2(source, target)
    logger.info('copy_created_successfully')
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
