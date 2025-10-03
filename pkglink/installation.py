import contextlib
import hashlib
import re
import shutil
from pathlib import Path

from hotlog import get_logger

from pkglink.models import SourceSpec
from pkglink.parsing import build_uv_install_spec
from pkglink.uvx import get_site_packages_path

logger = get_logger(__name__)


def _is_immutable_reference(spec: SourceSpec) -> bool:
    """Check if a source specification refers to an immutable reference that can be cached indefinitely."""
    if spec.source_type == 'package' and spec.version:
        # Package with specific version - immutable
        return True

    if spec.source_type == 'github' and spec.version:
        # GitHub with commit hash (40 char hex) - immutable
        if re.match(r'^[a-f0-9]{40}$', spec.version):
            return True
        # GitHub with semver-like version tag - generally immutable
        if re.match(r'^v?\d+\.\d+\.\d+', spec.version):
            return True

    # Everything else (branches, latest packages) - mutable
    return False


def _should_refresh_cache(cache_dir: Path, spec: SourceSpec) -> bool:
    """Determine if cache should be refreshed based on reference type."""
    if not cache_dir.exists():
        return True

    # For immutable references, never refresh our local cache
    # For mutable references, always refresh our local cache
    return not _is_immutable_reference(spec)


def _find_exact_package_match(
    install_dir: Path,
    expected_name: str,
) -> Path | None:
    """Find a directory that exactly matches the expected package name."""
    logger.debug(
        'looking_for_exact_package_match',
        expected=expected_name,
        directory=str(install_dir),
    )
    target = install_dir / expected_name
    if target.is_dir():
        logger.debug('exact_package_match_found', match=target.name)
        return target
    logger.debug('no_exact_package_match_found', expected=expected_name)
    return None


def _search_in_subdir(
    subdir_path: Path,
    subdir_name: str,
    expected_name: str,
    target_subdir: str,
) -> Path | None:
    """Search for package in a single platform subdirectory."""
    logger.debug('searching_in_platform_subdir', subdir=subdir_name)

    # Try exact match in this subdir
    result = _find_exact_package_match(subdir_path, expected_name)
    if result and (result / target_subdir).exists():
        logger.debug(
            'package_found_in_platform_subdir',
            path=str(result),
            subdir=subdir_name,
            target_subdir=target_subdir,
        )
        return result
    return None


def _search_in_site_packages(
    subdir_path: Path,
    subdir_name: str,
    expected_name: str,
    target_subdir: str,
) -> Path | None:
    """Search for package in site-packages within a platform subdirectory."""
    site_packages_path = subdir_path / 'site-packages'
    if not (site_packages_path.exists() and site_packages_path.is_dir()):
        return None

    logger.debug(
        'searching_in_site_packages',
        subdir=subdir_name,
        site_packages=str(site_packages_path),
    )
    result = _find_exact_package_match(site_packages_path, expected_name)
    if result and (result / target_subdir).exists():
        logger.debug(
            'package_found_in_site_packages',
            path=str(result),
            subdir=subdir_name,
            target_subdir=target_subdir,
        )
        return result
    return None


def _search_in_platform_subdirs(
    install_dir: Path,
    expected_name: str,
    target_subdir: str,
) -> Path | None:
    """Search for package in platform-specific subdirectories (Windows: Lib/, lib/, lib64/)."""
    for subdir_name in ['Lib', 'lib', 'lib64']:
        subdir_path = install_dir / subdir_name
        if not (subdir_path.exists() and subdir_path.is_dir()):
            continue

        # Try exact match in this subdir
        result = _search_in_subdir(
            subdir_path,
            subdir_name,
            expected_name,
            target_subdir,
        )
        if result:
            return result

        # Also try site-packages within this subdir (common on Windows)
        result = _search_in_site_packages(
            subdir_path,
            subdir_name,
            expected_name,
            target_subdir,
        )
        if result:
            return result
    return None


def find_package_root(
    install_dir: Path,
    expected_name: str,
    target_subdir: str = 'resources',
) -> Path:
    """Find the package directory using precise, CLI-driven detection.

    This function only uses exact matches and platform-specific subdirectory search.
    All fuzzy search strategies have been removed to avoid incorrect matches.
    """
    logger.debug(
        'looking_for_package_root',
        expected=expected_name,
        install_dir=str(install_dir),
    )

    # List all items for debugging
    items = list(install_dir.iterdir())
    logger.debug(
        'available_items_in_install_directory',
        items=[item.name for item in items],
        looking_for_subdir=target_subdir,
    )

    # Try exact match at the top level first
    result = _find_exact_package_match(install_dir, expected_name)
    if result and (result / target_subdir).exists():
        logger.debug(
            'package_root_found_exact_match',
            path=str(result),
            target_subdir=target_subdir,
        )
        return result

    # Try platform-specific subdirs (Windows: Lib/, lib/, lib64/)
    result = _search_in_platform_subdirs(
        install_dir,
        expected_name,
        target_subdir,
    )
    if result:
        return result

    # If exact match fails, clarify if package exists but subdir is missing
    package_exists = any(item.name == expected_name and item.is_dir() for item in items)
    if package_exists:
        message = f"Package '{expected_name}' found, but subdirectory '{target_subdir}' is missing in {install_dir}"
        warning_type = 'package_subdir_not_found'
    else:
        message = f"Package '{expected_name}' not found in {install_dir} (expected subdirectory '{target_subdir}')"
        warning_type = 'package_root_not_found'
    logger.warning(
        warning_type,
        message=message,
        expected=expected_name,
        install_dir=str(install_dir),
        target_subdir=target_subdir,
        suggestion='use of --from may be needed to specify correct module',
        available_directories=[
            item.name
            for item in items
            if item.is_dir() and not item.name.startswith('.') and not item.name.endswith('.dist-info')
        ],
    )
    raise RuntimeError(message)


def resolve_source_path(
    spec: SourceSpec,
    module_name: str | None = None,
    target_subdir: str = 'resources',
) -> Path:
    """Resolve source specification to an actual filesystem path."""
    logger.debug(
        'resolving_source_path',
        spec=spec.model_dump(),
        module=module_name,
        target_subdir=target_subdir,
    )

    # For all source types (including local), use uvx to install
    # This ensures we get the proper installed package structure
    target_module = module_name or spec.name
    logger.debug('target_module_to_find', module=target_module)

    # Use uvx to install the package
    logger.debug('attempting_uvx_installation')
    install_dir, _, _ = install_with_uvx(
        spec,
    )  # We don't need dist_info_name or dist_info_path here
    package_root = find_package_root(install_dir, target_module, target_subdir)
    logger.debug('successfully_resolved_via_uvx', path=str(package_root))
    return package_root


def _create_cache_directory(spec: SourceSpec, install_spec: str) -> Path:
    """Create a predictable cache directory for the package.

    Args:
        spec: Source specification
        install_spec: Built uv install specification

    Returns:
        Path to the cache directory
    """
    cache_base = Path.home() / '.cache' / 'pkglink'
    cache_base.mkdir(parents=True, exist_ok=True)

    # Use a hash of the install spec to create a unique cache directory
    spec_hash = hashlib.sha256(install_spec.encode()).hexdigest()[:8]
    return cache_base / f'{spec.name}_{spec_hash}'


def _get_cached_dist_info(cache_dir: Path) -> str | None:
    """Get cached dist_info_name if available.

    Args:
        cache_dir: Cache directory to check

    Returns:
        Cached dist_info_name or None
    """
    dist_info_cache_file = cache_dir / '.pkglink_dist_info'
    if not dist_info_cache_file.exists():
        return None

    try:
        return dist_info_cache_file.read_text().strip()
    except OSError:
        return None


def _prepare_cache_directory(cache_dir: Path, spec: SourceSpec) -> None:
    """Prepare cache directory by removing stale cache if needed.

    Args:
        cache_dir: Cache directory path
        spec: Source specification
    """
    if not cache_dir.exists():
        return

    logger.info(
        'refreshing_stale_cache',
        package=spec.name,
        _verbose_cache_dir=str(cache_dir),
    )
    with contextlib.suppress(OSError, FileNotFoundError):
        # Cache directory might have been removed by another process
        shutil.rmtree(cache_dir)


def _cache_dist_info(cache_dir: Path, dist_info_name: str | None) -> None:
    """Cache the dist_info_name for future use.

    Args:
        cache_dir: Cache directory
        dist_info_name: Dist info name to cache
    """
    if dist_info_name:
        dist_info_cache_file = cache_dir / '.pkglink_dist_info'
        dist_info_cache_file.write_text(dist_info_name)


def _perform_uvx_installation(
    spec: SourceSpec,
    install_spec: str,
    cache_dir: Path,
) -> tuple[Path, str, Path]:
    """Perform the actual uvx installation and cache setup.

    Args:
        spec: Source specification
        install_spec: Built uv install specification
        cache_dir: Cache directory to populate

    Returns:
        Tuple of (cache_dir, dist_info_name)

    Raises:
        RuntimeError: If uvx installation fails
    """
    try:
        # For mutable references (branches), force reinstall to get latest changes
        force_reinstall = not _is_immutable_reference(spec)

        if force_reinstall:
            logger.info(
                'downloading_package_with_uvx_force_reinstall',
                package=spec.name,
                source=install_spec,
                reason='mutable_reference',
            )
        else:
            logger.info(
                'downloading_package_with_uvx',
                package=spec.name,
                source=install_spec,
            )

        # Get the site-packages directory from uvx's environment
        site_packages, dist_info_name, dist_info_path = get_site_packages_path(
            install_spec,
            force_reinstall=force_reinstall,
            expected_package=spec.project_name,
        )
        logger.debug(
            'uvx_installed_to_site_packages',
            site_packages=str(site_packages),
            dist_info_name=dist_info_name,
            dist_info_path=str(dist_info_path),
        )

        # Debug: List contents of site-packages before copying
        site_packages_items = list(site_packages.iterdir())
        logger.debug(
            'site_packages_contents',
            items=[item.name for item in site_packages_items],
        )

        # Copy the site-packages to our cache directory
        shutil.copytree(site_packages, cache_dir)

        # Copy the dist-info directory using the exact path from uvx output
        if dist_info_path.exists():
            logger.debug(
                'copying_dist_info_from_uvx_path',
                source=str(dist_info_path),
                destination=str(cache_dir / dist_info_name),
            )
            shutil.copytree(
                dist_info_path,
                cache_dir / dist_info_name,
                dirs_exist_ok=True,
            )
        else:
            logger.warning(
                'dist_info_path_not_found',
                dist_info_path=str(dist_info_path),
                dist_info_name=dist_info_name,
            )
        # Cache the dist_info_name for future use
        _cache_dist_info(cache_dir, dist_info_name)

        logger.info(
            'package_downloaded_and_cached',
            package=spec.name,
            _verbose_cache_dir=str(cache_dir),
        )
    except RuntimeError as e:
        msg = f'Failed to install {spec.name} with uvx: {e}'
        raise RuntimeError(msg) from e
    else:
        return cache_dir, dist_info_name, dist_info_path


def install_with_uvx(spec: SourceSpec) -> tuple[Path, str, Path | None]:
    """Install package using uvx, then copy to a predictable location."""
    logger.debug('installing_using_uvx', package=spec.name)

    install_spec = build_uv_install_spec(spec)
    logger.debug(
        'install_spec',
        spec=install_spec,
        _verbose_source_spec=spec.model_dump(),
    )

    cache_dir = _create_cache_directory(spec, install_spec)

    # If already cached and shouldn't be refreshed, return the existing directory
    if cache_dir.exists() and not _should_refresh_cache(cache_dir, spec):
        logger.info(
            'using_cached_installation',
            package=spec.name,
            _verbose_cache_dir=str(cache_dir),
        )
        cached_dist_info_name = _get_cached_dist_info(cache_dir)
        # The following may happen due to previous incomplete installs
        # The suggestion should work to get things back on track.
        if cached_dist_info_name is None:  # pragma: no cover
            msg = (
                f'\n[ERROR] Cached dist-info name missing for package: {spec.name}\n'
                f'  Cache directory: {cache_dir}\n'
                f'  Suggestion: Delete this directory and retry.\n'
                f'    rm -rf {cache_dir}\n'
                f'  This will force a fresh install and resolve the issue.\n'
            )
            raise RuntimeError(msg)
        # For cached installs, we don't have the dist_info_path, so return None for it
        return cache_dir, cached_dist_info_name, None

    # Remove stale cache if it exists and needs refresh
    _prepare_cache_directory(cache_dir, spec)

    # Perform the installation
    return _perform_uvx_installation(spec, install_spec, cache_dir)
