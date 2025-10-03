"""Package discovery and metadata extraction."""

import configparser
from pathlib import Path

from hotlog import get_logger

from pkglink.models import PackageInfo

logger = get_logger(__name__)


def parse_entry_points(file_path: Path) -> dict[str, str]:
    """Parse entry_points.txt file for console scripts.

    Args:
        file_path: Path to the entry_points.txt file.

    Returns:
        A dictionary mapping console script names to their targets.
    """
    scripts: dict[str, str] = {}
    if not file_path.exists():
        return scripts

    config = configparser.ConfigParser()
    config.read(file_path)

    if 'console_scripts' in config:
        scripts = dict(config['console_scripts'])
    return scripts


def parse_metadata_file(file_path: Path) -> dict[str, str]:
    """Parse METADATA file for package information.

    Args:
        file_path: Path to the METADATA file.

    Returns:
        A dictionary mapping package metadata fields to their values.
        Returns an empty dictionary if the file does not exist or contains no valid metadata.
    """
    metadata = {}
    if not file_path.exists():
        return metadata

    content = file_path.read_text()
    for line in content.split('\n'):
        if ':' in line and not line.startswith(' '):
            key, value = line.split(':', 1)
            metadata[key.strip().lower().replace('-', '_')] = value.strip()
    return metadata


def _extract_package_info_from_dist_info(
    dist_info_dir: Path,
    cache_dir: Path,
) -> PackageInfo:
    """Extract package information from a specific dist-info directory.

    Args:
        dist_info_dir: Path to the .dist-info directory
        cache_dir: Path to the cache directory (for dependency extraction)

    Returns:
        PackageInfo object with extracted metadata
    """
    # Extract package name and version from dist-info directory name
    # Format looks as follows: package_name-version.dist-info
    name_version = dist_info_dir.name.replace('.dist-info', '')
    parts = name_version.split('-')

    # Defensive: malformed dist-info names are not expected with uv; raise error if encountered
    if len(parts) < 2:  # pragma: no cover
        msg = (
            f'Malformed dist-info directory name:\n'
            f"  '{dist_info_dir.name}'\n"
            f'Expected format: package_name-version.dist-info\n'
            f'This likely indicates a corrupted cache or environment.\n'
            f'Please check your uv cache and remove any invalid entries.'
        )
        raise RuntimeError(msg)

    # Version is everything after the first part (package name)
    actual_package_name = parts[0]
    version = '-'.join(parts[1:])

    # Parse entry points and metadata
    entry_points_file = dist_info_dir / 'entry_points.txt'
    console_scripts = parse_entry_points(entry_points_file)

    metadata_file = dist_info_dir / 'METADATA'
    metadata = parse_metadata_file(metadata_file)

    dependencies = _extract_dependencies_from_cache(
        cache_dir,
        actual_package_name,
    )

    return PackageInfo(
        version=version,
        console_scripts=console_scripts,
        metadata=metadata,
        dependencies=dependencies,
    )


def extract_package_metadata(
    cache_dir: Path,
    dist_info_name: str,
) -> PackageInfo:
    """Extract package metadata using exact dist-info directory name from uvx.

    Args:
        cache_dir: Path to the uvx cache directory
        dist_info_name: Exact name of the .dist-info directory (e.g., 'test_cli-0.1.0.dist-info')

    Returns:
        PackageInfo object with extracted metadata

    Raises:
        RuntimeError: If the dist-info directory doesn't exist
    """
    dist_info_dir = cache_dir / dist_info_name

    # Defensive: This should never happen if uv manages the cache correctly.
    # This is a debugging helper for unexpected/corrupted environments.
    if not dist_info_dir.exists():  # pragma: no cover
        msg = f'Dist-info directory {dist_info_name} not found in {cache_dir}'
        raise RuntimeError(msg)

    logger.debug(
        'using_exact_dist_info_from_uvx',
        dist_info_name=dist_info_name,
    )
    package_info = _extract_package_info_from_dist_info(
        dist_info_dir,
        cache_dir,
    )
    logger.debug(
        'extracted_package_metadata_from_uvx_hint',
        **package_info.model_dump(),
    )
    return package_info


def _extract_dependencies_from_cache(
    cache_dir: Path,
    main_package: str,
) -> list[str]:
    """Extract all dependencies with versions from uvx cache directory.

    Args:
        cache_dir: Path to the uvx cache directory
        main_package: Name of the main package to exclude from dependencies

    Returns:
        List of dependency specifications like ['pydantic>=2.11.9', 'rich>=14.1.0', ...]
    """
    dependencies = []

    # Find all dist-info directories
    dist_info_dirs = list(cache_dir.rglob('*.dist-info'))

    for dist_info_dir in dist_info_dirs:
        # Parse package name and version from dist-info directory name
        # Format looks as follows: package_name-version.dist-info
        name_version = dist_info_dir.name.replace('.dist-info', '')

        # Split on '-' but be careful with package names that contain hyphens
        parts = name_version.split('-')

        # Defensive: malformed dist-info names are not expected with uv.
        # This branch is unreachable in normal operation
        if len(parts) < 2:  # pragma: no cover
            continue

        # The version is typically the last part that looks like a version
        # Package name is everything before the version
        version = parts[-1]
        package_name = '-'.join(parts[:-1])

        # Skip the main package itself and common virtual environment files
        skip_packages = [
            main_package.lower(),
            '_virtualenv',
            'pip',
            'setuptools',
            'wheel',
        ]
        if package_name.lower() in skip_packages:
            continue

        # Add as dependency with minimum version constraint
        dependencies.append(f'{package_name}>={version}')

    logger.debug(
        'extracted_dependencies_from_cache',
        count=len(dependencies),
        dependencies=dependencies,
        main_package=main_package,
    )

    return sorted(dependencies)
