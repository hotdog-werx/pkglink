import contextlib
import hashlib
import re
import shutil
import subprocess
from difflib import SequenceMatcher
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


def find_python_package(install_dir: Path) -> Path | None:
    """Find the first directory with __init__.py (Python package)."""
    logger.debug('looking_for_python_package', directory=str(install_dir))
    for item in install_dir.iterdir():
        if item.is_dir() and (item / '__init__.py').exists():
            logger.debug('python_package_found', package=item.name)
            return item
    logger.debug('no_python_package_found', directory=str(install_dir))
    return None


def find_with_resources(install_dir: Path) -> Path | None:
    """Find the first directory containing 'resources' folder."""
    logger.debug(
        'looking_for_directory_with_resources',
        directory=str(install_dir),
    )
    for item in install_dir.iterdir():
        if item.is_dir() and (item / 'resources').exists():
            logger.debug('directory_with_resources_found', directory=item.name)
            return item
    logger.debug(
        'no_directory_with_resources_found',
        directory=str(install_dir),
    )
    return None


def find_exact_match(install_dir: Path, expected_name: str) -> Path | None:
    """Find a directory that exactly matches the expected name."""
    logger.debug(
        'looking_for_exact_match',
        expected=expected_name,
        directory=str(install_dir),
    )
    target = install_dir / expected_name
    if target.is_dir():
        logger.debug('exact_match_found', match=target.name)
        return target
    logger.debug('no_exact_match_found', expected=expected_name)
    return None


def find_by_prefix(install_dir: Path, expected_name: str) -> Path | None:
    """Find a directory that starts with the expected name."""
    logger.debug(
        'looking_for_prefix_match',
        prefix=expected_name,
        directory=str(install_dir),
    )
    for item in install_dir.iterdir():
        if item.is_dir() and item.name.startswith(expected_name):
            logger.debug('prefix_match_found', match=item.name)
            return item
    logger.debug('no_prefix_match_found', expected=expected_name)
    return None


def find_by_suffix(install_dir: Path, expected_name: str) -> Path | None:
    """Find a directory that ends with the expected name."""
    logger.debug(
        'looking_for_suffix_match',
        suffix=expected_name,
        directory=str(install_dir),
    )
    for item in install_dir.iterdir():
        if item.is_dir() and item.name.endswith(expected_name):
            logger.debug('suffix_match_found', match=item.name)
            return item
    logger.debug('no_suffix_match_found', expected=expected_name)
    return None


def find_by_similarity(install_dir: Path, expected_name: str) -> Path | None:
    """Find a directory with the highest similarity to the expected name."""
    logger.debug(
        'looking_for_similarity_match',
        expected=expected_name,
        directory=str(install_dir),
    )
    best_match = None
    best_ratio = 0.6  # Minimum similarity threshold

    for item in install_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.') and not item.name.endswith('.dist-info'):
            ratio = SequenceMatcher(
                None,
                expected_name.lower(),
                item.name.lower(),
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = item

    if best_match:
        logger.debug(
            'similarity_match_found',
            match=best_match.name,
            ratio=best_ratio,
        )
        return best_match

    logger.debug('no_similarity_match_found', expected=expected_name)
    return None


def find_first_directory(install_dir: Path) -> Path | None:
    """Find the first non-hidden, non-dist-info directory."""
    logger.debug('looking_for_first_directory', directory=str(install_dir))
    for item in install_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.') and not item.name.endswith('.dist-info'):
            logger.debug('first_directory_found', directory=item.name)
            return item
    logger.debug('no_suitable_directory_found', directory=str(install_dir))
    return None


def _try_package_root_strategies(
    install_dir: Path,
    expected_name: str,
    target_subdir: str,
) -> Path | None:
    strategies = [
        find_exact_match,
        find_python_package,
        find_with_resources,
        find_by_prefix,
        find_by_suffix,
        find_by_similarity,
        find_first_directory,
    ]
    for strategy in strategies:
        if strategy in [
            find_python_package,
            find_with_resources,
            find_first_directory,
        ]:
            result = strategy(install_dir)
        else:
            result = strategy(install_dir, expected_name)
        if result and (result / target_subdir).exists():
            logger.debug(
                'package_root_found',
                strategy=strategy.__name__,
                path=str(result),
                target_subdir=target_subdir,
            )
            return result
    return None


def _search_in_subdir_and_site_packages(
    subdir_path: Path,
    subdir_name: str,
    expected_name: str,
    target_subdir: str,
) -> Path | None:  # pragma: no cover - Windows-specific
    """Search for package in a subdirectory and its site-packages."""
    logger.debug('retrying_in_subdirectory', subdir=subdir_name)
    result = _try_package_root_strategies(
        subdir_path,
        expected_name,
        target_subdir,
    )
    if result:
        logger.debug(
            'package_root_found',
            strategy='subdir',
            path=str(result),
            subdir=subdir_name,
        )
        return result

    # Also try site-packages within this subdir (common on Windows)
    site_packages_path = subdir_path / 'site-packages'
    if site_packages_path.exists() and site_packages_path.is_dir():
        logger.debug(
            'retrying_in_site_packages',
            subdir=subdir_name,
            site_packages=str(site_packages_path),
        )
        result = _try_package_root_strategies(
            site_packages_path,
            expected_name,
            target_subdir,
        )
        if result:
            logger.debug(
                'package_root_found',
                strategy='site_packages',
                path=str(result),
                subdir=subdir_name,
            )
            return result
    return None


def _try_windows_lib_subdirs(
    install_dir: Path,
    expected_name: str,
    target_subdir: str,
) -> Path | None:  # pragma: no cover - Windows-specific
    """Try common Windows subdirs (Lib/, lib/, lib64/) and site-packages for package root."""
    for subdir in ['Lib', 'lib', 'lib64']:
        subdir_path = install_dir / subdir
        if subdir_path.exists() and subdir_path.is_dir():
            result = _search_in_subdir_and_site_packages(
                subdir_path,
                subdir,
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
    """Find the actual package directory after installation using multiple strategies."""
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

    # Try strategies at the top level
    result = _try_package_root_strategies(
        install_dir,
        expected_name,
        target_subdir,
    )
    if result:
        return result

    # Try common subdirs (Windows: Lib/, lib/, lib64/)
    result = _try_windows_lib_subdirs(install_dir, expected_name, target_subdir)
    if result:
        return result  # pragma: no cover - we may hit this in CI but not in mac or linux

    # If all strategies fail, provide detailed error
    logger.error(
        'package_root_not_found',
        expected=expected_name,
        install_dir=str(install_dir),
    )
    logger.error(
        'available_directories',
        directories=[
            item.name
            for item in items
            if item.is_dir() and not item.name.startswith('.') and not item.name.endswith('.dist-info')
        ],
    )
    msg = f'Package root {expected_name} not found in {install_dir} (and common subdirs)'
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
