import contextlib
import hashlib
import re
import shutil
import subprocess
from pathlib import Path

from pkglink.logging import get_logger
from pkglink.models import SourceSpec
from pkglink.parsing import build_uv_install_spec

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
    try:
        items = list(install_dir.iterdir())
        logger.debug(
            'available_items_in_install_directory',
            items=[item.name for item in items],
        )
    except OSError as e:
        logger.exception(
            'error_listing_install_directory',
            install_dir=str(install_dir),
            error=str(e),
        )
        msg = f'Error accessing install directory {install_dir}: {e}'
        raise RuntimeError(msg) from e

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

    # If exact match fails, provide detailed error
    logger.error(
        'package_root_not_found',
        expected=expected_name,
        install_dir=str(install_dir),
        target_subdir=target_subdir,
    )
    logger.error(
        'available_directories',
        directories=[
            item.name
            for item in items
            if item.is_dir() and not item.name.startswith('.') and not item.name.endswith('.dist-info')
        ],
    )
    msg = f'Package "{expected_name}" not found in {install_dir}'
    raise RuntimeError(msg)


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
    install_dir = install_with_uvx(spec)
    package_root = find_package_root(install_dir, target_module, target_subdir)
    logger.debug('successfully_resolved_via_uvx', path=str(package_root))
    return package_root


def install_with_uvx(spec: SourceSpec) -> Path:
    """Install package using uvx, then copy to a predictable location."""
    logger.debug('installing_using_uvx', package=spec.name)

    install_spec = build_uv_install_spec(spec)
    logger.debug(
        'install_spec',
        spec=install_spec,
        _verbose_source_spec=spec.model_dump(),
    )

    # Create a predictable cache directory that we control
    cache_base = Path.home() / '.cache' / 'pkglink'
    cache_base.mkdir(parents=True, exist_ok=True)

    # Use a hash of the install spec to create a unique cache directory
    # Remove the inline import
    spec_hash = hashlib.sha256(install_spec.encode()).hexdigest()[:8]
    cache_dir = cache_base / f'{spec.name}_{spec_hash}'

    # If already cached and shouldn't be refreshed, return the existing directory
    if cache_dir.exists() and not _should_refresh_cache(cache_dir, spec):
        logger.info(
            'using_cached_installation',
            package=spec.name,
            _verbose_cache_dir=str(cache_dir),
        )
        return cache_dir

    # Remove stale cache if it exists and needs refresh
    if cache_dir.exists():
        logger.info(
            'refreshing_stale_cache',
            package=spec.name,
            _verbose_cache_dir=str(cache_dir),
        )
        with contextlib.suppress(OSError, FileNotFoundError):
            # Cache directory might have been removed by another process
            shutil.rmtree(cache_dir)

    try:
        # Use uvx to install, then use uvx to run a script that tells us the site-packages
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

        cmd = ['uvx']
        if force_reinstall:
            cmd.append('--force-reinstall')
        cmd.extend(
            [
                '--from',
                install_spec,
                'python',
                '-c',
                'import site; print(site.getsitepackages()[0])',
            ],
        )
        logger.debug('running_uvx_command', _debug_command=' '.join(cmd))

        result = subprocess.run(  # noqa: S603 - executing uvx
            cmd,
            capture_output=True,
            text=True,
            check=True,
            shell=False,
        )

        # Get the site-packages directory from uvx's environment
        site_packages = Path(result.stdout.strip())
        logger.debug(
            'uvx_installed_to_site_packages',
            site_packages=str(site_packages),
        )

        # Copy the site-packages to our cache directory
        shutil.copytree(site_packages, cache_dir)
        logger.info(
            'package_downloaded_and_cached',
            package=spec.name,
            _verbose_cache_dir=str(cache_dir),
        )

    except subprocess.CalledProcessError as e:
        logger.exception('uvx installation failed')
        msg = f'Failed to install {spec.name} with uvx: {e.stderr}'
        raise RuntimeError(msg) from e
    else:
        return cache_dir
