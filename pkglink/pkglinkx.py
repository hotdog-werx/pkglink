"""pkglinkx: Create uvx-compatible package structures from GitHub repos."""

import configparser
import contextlib
import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from pkglink.logging import get_logger
from pkglink.models import SourceSpec
from pkglink.parsing import determine_install_spec_and_module

logger = get_logger(__name__)


class PkglinkxMetadata(BaseModel):
    """Metadata for pkglinkx installations."""
    
    version: str
    source_hash: str
    install_spec: str
    package_name: str
    console_scripts: dict[str, str] = {}
    last_refreshed: str


def parse_entry_points(file_path: Path) -> dict[str, str]:
    """Parse entry_points.txt file for console scripts."""
    scripts = {}
    
    if not file_path.exists():
        return scripts
    
    config = configparser.ConfigParser()
    config.read(file_path)
    
    if 'console_scripts' in config:
        scripts = dict(config['console_scripts'])
    
    return scripts


def parse_metadata_file(file_path: Path) -> dict[str, Any]:
    """Parse METADATA file for package information."""
    metadata = {}
    
    if not file_path.exists():
        return metadata
    
    content = file_path.read_text()
    for line in content.split('\n'):
        if ':' in line and not line.startswith(' '):
            key, value = line.split(':', 1)
            metadata[key.strip().lower().replace('-', '_')] = value.strip()
    
    return metadata


def generate_pyproject_toml(
    package_name: str,
    version: str,
    console_scripts: dict[str, str],
    metadata: dict[str, Any],
) -> str:
    """Generate pyproject.toml content from package metadata."""
    
    # Convert package name for project name (underscores to hyphens)
    project_name = package_name.replace('_', '-')
    
    # Build scripts section
    scripts_lines = []
    for cmd_name, target in console_scripts.items():
        scripts_lines.append(f'{cmd_name} = "{target}"')
    
    scripts_section = '\n'.join(scripts_lines) if scripts_lines else '# No console scripts found'
    
    # Get description and python requirement
    description = metadata.get('description', f'{project_name} package')
    requires_python = metadata.get('requires_python', '>=3.11')
    
    return f"""[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{project_name}"
version = "{version}"
description = "{description}"
requires-python = "{requires_python}"

[project.scripts]
{scripts_section}
"""


def extract_package_info(cache_dir: Path, package_name: str) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Extract version, console scripts, and metadata from cached package."""
    
    # Find dist-info directory
    dist_info_pattern = f"{package_name}-*.dist-info"
    dist_info_dirs = list(cache_dir.glob(dist_info_pattern))
    
    if not dist_info_dirs:
        raise RuntimeError(f"No dist-info directory found for {package_name} in {cache_dir}")
    
    dist_info_dir = dist_info_dirs[0]
    
    # Extract version from directory name (e.g., "test_cli-0.1.0.dist-info" -> "0.1.0")
    # Remove the ".dist-info" suffix and split on '-' to get version part
    name_without_suffix = dist_info_dir.name.replace('.dist-info', '')
    parts = name_without_suffix.split('-')
    # Version is everything after the package name
    version = '-'.join(parts[1:])
    
    # Parse entry points for console scripts
    entry_points_file = dist_info_dir / "entry_points.txt"
    console_scripts = parse_entry_points(entry_points_file)
    
    # Parse metadata file
    metadata_file = dist_info_dir / "METADATA"
    metadata = parse_metadata_file(metadata_file)
    
    logger.debug(
        'extracted_package_info',
        version=version,
        console_scripts=console_scripts,
        package_name=package_name,
    )
    
    return version, console_scripts, metadata


def create_pkglink_structure(
    install_spec: SourceSpec,
    cache_dir: Path,
    package_name: str,
    target_dir: Path,
) -> None:
    """Create .pkglink directory structure for uvx compatibility."""
    
    # Extract package information from cached installation
    version, console_scripts, metadata = extract_package_info(cache_dir, package_name)
    
    # Create target directory
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Create src directory and symlink the package source
    src_dir = target_dir / "src"
    src_dir.mkdir(exist_ok=True)
    
    package_symlink = src_dir / package_name
    package_source = cache_dir / package_name
    
    # Remove existing symlink if it exists
    if package_symlink.exists():
        package_symlink.unlink()
    
    # Create symlink to the actual package source
    package_symlink.symlink_to(package_source, target_is_directory=True)
    
    logger.info(
        'created_package_symlink',
        source=str(package_source),
        target=str(package_symlink),
    )
    
    # Generate and write pyproject.toml
    pyproject_content = generate_pyproject_toml(package_name, version, console_scripts, metadata)
    pyproject_file = target_dir / "pyproject.toml"
    pyproject_file.write_text(pyproject_content)
    
    logger.info(
        'created_pyproject_toml',
        file=str(pyproject_file),
        console_scripts=list(console_scripts.keys()),
    )
    
    # Create metadata for version tracking
    metadata_content = PkglinkxMetadata(
        version=version,
        source_hash=cache_dir.name.split('_')[-1],  # Extract hash from cache dir name
        install_spec=str(install_spec.model_dump()),
        package_name=package_name,
        console_scripts=console_scripts,
        last_refreshed=str(Path().cwd())  # Simple timestamp placeholder
    )
    
    metadata_file = target_dir / ".pkglink-metadata.yaml"
    with metadata_file.open('w') as f:
        yaml.dump(metadata_content.model_dump(), f)
    
    logger.info('created_pkglink_metadata', file=str(metadata_file))


def force_uvx_refresh(target_dir: Path, cache_dir: Path, package_name: str) -> None:
    """Force uvx to refresh the package cache."""
    
    logger.info('forcing_uvx_refresh', package=package_name)
    
    # Force uvx to install from local directory
    cmd = [
        'uvx',
        '--refresh-package', package_name,
        '--from', str(target_dir),
        '--help'  # Just trigger installation without running anything
    ]
    
    logger.debug('running_uvx_refresh_command', command=' '.join(cmd))
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,  # Don't fail if uvx returns non-zero
    )
    
    if result.returncode == 0:
        logger.info('uvx_refresh_successful', package=package_name)
    else:
        logger.warning(
            'uvx_refresh_failed',
            package=package_name,
            stderr=result.stderr,
            stdout=result.stdout,
        )


def check_version_changed(target_dir: Path, current_spec: str, current_hash: str) -> bool:
    """Check if we need to refresh based on version/hash changes."""
    
    metadata_file = target_dir / ".pkglink-metadata.yaml"
    
    if not metadata_file.exists():
        logger.debug('no_existing_metadata_refresh_needed')
        return True  # First install
    
    try:
        with metadata_file.open() as f:
            existing_metadata = yaml.safe_load(f)
        
        existing_hash = existing_metadata.get('source_hash')
        existing_spec = existing_metadata.get('install_spec')
        
        changed = (existing_hash != current_hash or existing_spec != current_spec)
        
        logger.debug(
            'version_change_check',
            changed=changed,
            existing_hash=existing_hash,
            current_hash=current_hash,
        )
        
        return changed
    
    except Exception as e:
        logger.warning('failed_to_read_metadata_assuming_changed', error=str(e))
        return True


def pkglinkx_main(source_spec: str) -> None:
    """Main pkglinkx entry point."""
    
    logger.info('starting_pkglinkx', source=source_spec)
    
    # Parse source spec using existing pkglink logic
    from pkglink.models import CliArgs
    
    args = CliArgs(
        source=source_spec,
        directory='.',  # Not used for pkglinkx
        dry_run=False,
        force=False,
        verbose=False,
        symlink_name=None,
    )
    
    install_spec, module_name = determine_install_spec_and_module(args)
    
    logger.debug(
        'parsed_source_spec',
        install_spec=install_spec.model_dump(),
        module_name=module_name,
    )
    
    # Use our local uvx installation function to get cached source
    cache_dir = install_with_uvx(install_spec)
    
    # Create .pkglink target directory
    pkglink_base = Path('.pkglink')
    target_dir = pkglink_base / install_spec.name
    
    # Check if refresh is needed
    current_hash = cache_dir.name.split('_')[-1]
    current_spec = str(install_spec.model_dump())
    needs_refresh = check_version_changed(target_dir, current_spec, current_hash)
    
    # Create/update .pkglink structure
    create_pkglink_structure(install_spec, cache_dir, module_name, target_dir)
    
    # Force uvx refresh if needed
    if needs_refresh:
        force_uvx_refresh(target_dir, cache_dir, module_name)
    
    logger.info(
        'pkglinkx_completed',
        target_dir=str(target_dir),
        package=module_name,
        refreshed=needs_refresh,
    )
    
    print("✅ pkglinkx completed! You can now use:")
    print(f"   uvx --from {target_dir} <command>")


def main() -> None:
    """Main entry point for pkglinkx CLI."""
    import sys
    if len(sys.argv) != 2:
        print("Usage: pkglinkx <github:org/repo[@version]>")
        sys.exit(1)
    
    pkglinkx_main(sys.argv[1])


if __name__ == '__main__':
    main()


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


def install_with_uvx(spec: SourceSpec) -> Path:
    """Install package using uvx, then copy to a predictable location."""
    logger.debug('installing_using_uvx', package=spec.name)

    from pkglink.parsing import build_uv_install_spec
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
