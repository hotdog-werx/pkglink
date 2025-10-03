"""Symlink management utilities."""

import os
import shutil
import tempfile
from pathlib import Path

from hotlog import get_logger

logger = get_logger(__name__)


def _cleanup_symlink_test(
    test_link: Path,
    test_path: Path,
) -> None:  # pragma: no cover - Windows-specific
    try:
        if test_link.exists():
            test_link.unlink()
        if test_path.exists():
            test_path.unlink()
    except OSError:
        pass


def _can_create_symlink_in_tmpdir() -> bool:  # pragma: no cover - Windows-specific
    """Attempt to create a symlink in a temp dir. Return True if successful, False otherwise."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_path = Path(tmpdir) / 'symlink_test_target'
        test_link = Path(tmpdir) / 'symlink_test_link'
        test_path.write_text('test')
        try:
            test_link.symlink_to(test_path)
            result = test_link.is_symlink()
        except OSError:
            result = False
        _cleanup_symlink_test(test_link, test_path)
        return result


def supports_symlinks() -> bool:
    """Check if the current system supports symlinks (and has permission)."""
    if not hasattr(os, 'symlink'):
        return False
    if os.name != 'nt':
        return True  # pragma: no cover - Winddows will not hit this line
    return _can_create_symlink_in_tmpdir()  # pragma: no cover - Windows-specific


def create_symlink(
    source: Path,
    target: Path,
    *,
    force: bool = False,
    allow_additional_symlink_removal: bool = False,
) -> bool:
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
            remove_target(
                target,
                expected_name=target.name,
                allow_additional_symlink_removal=allow_additional_symlink_removal,
            )
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
        # Ensure parent directories exist for the target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source, target_is_directory=source.is_dir())
        logger.info('symlink_created_successfully')
        return True

    # Fallback to copying
    logger.debug('symlinks_not_supported_falling_back_to_copy')
    # Ensure parent directories exist for the target
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        logger.debug('copying_directory_tree')
        shutil.copytree(source, target)
    else:
        logger.debug('copying_file')
        shutil.copy2(source, target)
    logger.info('copy_created_successfully')
    return False


def _check_not_dot_or_dotdot(
    resolved_name: str,
    target: Path,
    resolved_target: Path,
) -> None:
    # Defensive: This check is not practically reachable via normal filesystem operations,
    # because you cannot create files or directories named '.' or '..'. These are always interpreted
    # as the current or parent directory by the OS and pathlib. Retained for defense-in-depth in case
    # a malicious Path object is constructed elsewhere in the codebase. See tests for details.
    if resolved_name in {'.', '..'}:  # pragma: no cover
        logger.error(
            'refusing_to_remove_dot_or_dotdot',
            target=str(target),
            resolved_target=str(resolved_target),
            resolved_name=resolved_name,
        )
        msg = f"Refusing to remove '{resolved_name}' (resolved from {target})"
        raise ValueError(msg)


def _check_name_match(
    target_name: str,
    expected_name: str,
    target: Path,
) -> None:
    if target_name != expected_name:
        logger.error(
            'refusing_to_remove_target_name_mismatch',
            target=str(target),
            target_name=target_name,
            expected_name=expected_name,
        )
        msg = f'Refusing to remove target: name mismatch. Expected "{expected_name}", got "{target_name}"'
        raise ValueError(msg)


def _check_path_traversal(target_name: str, target: Path) -> None:
    # Defensive: This check is not practically reachable via normal filesystem operations,
    # because you cannot create files or directories with '/' or '\\' in the name, and '..' is always
    # interpreted as the parent directory. Retained for defense-in-depth in case a malicious Path object
    # is constructed elsewhere in the codebase. See tests for details.
    if '..' in target_name or '/' in target_name or '\\' in target_name:  # pragma: no cover
        logger.error(
            'refusing_to_remove_target_with_path_traversal',
            target=str(target),
            target_name=target_name,
        )
        msg = f'Refusing to remove target with path traversal characters: {target}'
        raise ValueError(msg)


def _check_common_removal_safety(target: Path) -> None:
    cwd = Path.cwd().resolve()
    # Check the symlink's location, not its resolved destination
    if not str(target).startswith(str(cwd)):
        msg = f'Refusing to remove target outside working directory: {target}'
        raise ValueError(msg)
    if any(part == '.git' for part in target.parts):
        msg = 'Refusing to remove .git directory or its contents'
        raise ValueError(msg)


def _check_additional_symlink_removal(target: Path) -> None:
    if not target.is_symlink():
        msg = 'Refusing to remove non-symlink for additional link'
        raise ValueError(msg)


def _check_normal_removal(
    target_name: str,
    target: Path,
    resolved_name: str,
    resolved_target: Path,
    expected_name: str,
) -> None:
    _check_not_dot_or_dotdot(resolved_name, target, resolved_target)
    _check_name_match(target_name, expected_name, target)
    _check_path_traversal(target_name, target)


def remove_target(
    target: Path,
    *,
    expected_name: str,
    allow_additional_symlink_removal: bool = False,
) -> None:
    """Remove a target file or directory (symlink or copy).

    Safety checks:
    1. Target must be inside cwd
    2. Never remove .git or its contents
    3. For additional symlinks: must be symlink, skip other checks
    4. For normal: run all checks
    """
    target_name = target.name
    resolved_target = target.resolve()
    resolved_name = resolved_target.name
    _check_common_removal_safety(target)
    if allow_additional_symlink_removal:
        _check_additional_symlink_removal(target)
    else:
        _check_normal_removal(
            target_name,
            target,
            resolved_name,
            resolved_target,
            expected_name,
        )

    logger.debug('removing_target', target=str(target), target_name=target_name)
    if target.is_symlink():
        logger.debug('removing_symlink')
        target.unlink()
        return
    if target.is_dir():
        logger.debug('removing_directory')
        shutil.rmtree(target)
        return
    if target.is_file():
        logger.debug('removing_file')
        target.unlink()
        return
    logger.warning(
        'target_does_not_exist_or_unrecognized_type',
        target=str(target),
    )
