"""Module for interacting with uvx (uv's tool runner)."""

import datetime
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

from hotlog import get_logger

logger = get_logger(__name__)


def _run_uvx_subprocess(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Internal helper to run uvx subprocess commands safely.

    This is the only function that should use subprocess.run with uvx.
    """
    logger.debug('running_uvx_command', command=' '.join(cmd))
    env = None
    github_token = os.environ.get('GITHUB_TOKEN')
    if github_token:
        env = os.environ.copy()
        env['GITHUB_TOKEN'] = github_token
    return subprocess.run(  # noqa: S603 - executing uvx
        cmd,
        capture_output=True,
        text=True,
        check=False,  # Let callers handle return codes
        shell=False,
        env=env,
    )


def _build_site_packages_command(
    install_spec: str,
    *,
    force_reinstall: bool = False,
) -> list[str]:
    """Build the uvx command to get site-packages path.

    Args:
        install_spec: The package specification to install
        force_reinstall: Whether to force reinstall the package

    Returns:
        Complete uvx command as list of strings
    """
    cmd = ['uvx', '--verbose']
    if force_reinstall:
        cmd.append('--force-reinstall')

    # For local wheel installs, --force-reinstall should be sufficient.
    # Using --no-cache here would leave behind temporary environments, so we avoid it.

    cmd.extend(
        [
            '--from',
            install_spec,
            'python',
            '-c',
            'import site; print(site.getsitepackages()[0])',
        ],
    )
    return cmd


def _normalize_name(name: str) -> str:
    """Normalize package/dist-info names for matching."""
    return name.lower().replace('-', '_').replace('.', '_')


def _extract_dist_info_path(
    stderr_output: str,
    expected_package: str,
) -> tuple[str, Path]:
    """Extract dist-info directory name and full path for the expected package from uvx verbose stderr output.

    Args:
        stderr_output: The stderr output from uvx --verbose
        expected_package: The package name to match (required)

    Returns:
        Tuple of (dist-info directory name, full path)

    Raises:
        RuntimeError: If no dist-info is found
    """
    dist_info_candidates = []
    stderr_lines = stderr_output.split('\n')
    for line in stderr_lines:
        if 'Looking at `.dist-info` at:' in line:
            # Extract the full path from the line
            match = re.search(r'at: (.*[\\/][^\\/]+\.dist-info)', line)
            if match:
                full_path = match.group(1).strip()
                dist_info_name = Path(full_path).parts[-1]
                dist_info_candidates.append((dist_info_name, Path(full_path)))

    logger.debug(
        'all_dist_info_paths_found',
        dist_info_candidates=[(n, str(p)) for n, p in dist_info_candidates],
        uvx_stderr_lines=len(stderr_lines),
    )
    # Find the candidate matching the expected package
    for name, path in dist_info_candidates:
        if _normalize_name(expected_package) in _normalize_name(name):
            return name, path
    error_msg = (
        f"Could not find dist-info for expected package '{expected_package}'.\n"
        'If installing from GitHub, you may need to provide --project-name matching the PyPI/project name.\n'
        f'Found dist-info candidates: {dist_info_candidates} (stderr lines: {len(stderr_lines)})'
    )
    raise RuntimeError(error_msg)


def _get_cache_busting_version(build_root: Path, timestamp: str) -> str:
    """Get the cache-busting version for a project."""
    pyproject_path = build_root / 'pyproject.toml'
    base_version = '0.0.0'

    if not pyproject_path.exists():
        return f'{base_version}.post{timestamp}'

    pyproject_text = pyproject_path.read_text()
    dynamic_match = re.search(
        r'dynamic\s*=\s*\[(?P<values>[^\]]*)\]',
        pyproject_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    dynamic_version = bool(
        dynamic_match and 'version' in dynamic_match.group('values'),
    )

    if dynamic_version:
        return _get_dynamic_version_cache_bust(
            pyproject_text,
            build_root,
            timestamp,
            base_version,
        )
    return _get_static_version_cache_bust(
        pyproject_text,
        pyproject_path,
        timestamp,
        base_version,
    )


def _get_dynamic_version_cache_bust(
    pyproject_text: str,
    build_root: Path,
    timestamp: str,
    base_version: str,
) -> str:
    """Handle cache-busting for dynamic version projects."""
    version_path_match = re.search(
        r'version\.path\s*=\s*["\']([^"\']+)["\']',
        pyproject_text,
    )
    if not version_path_match:
        logger.debug('dynamic_version_path_missing', path='(unspecified)')
        return f'{base_version}.post{timestamp}'

    version_file = build_root / version_path_match.group(1)
    if not version_file.exists():
        logger.debug('dynamic_version_path_missing', path=str(version_file))
        return f'{base_version}.post{timestamp}'

    version_text = version_file.read_text()
    version_value = re.search(
        r'__version__\s*=\s*["\']([^"\']+)["\']',
        version_text,
    )

    cache_busting_version = f'{base_version}.post{timestamp}'
    if version_value:
        base_version = version_value.group(1)
        cache_busting_version = f'{base_version}.post{timestamp}'
        updated_version_text = re.sub(
            r'(__version__\s*=\s*["\'])([^"\']+)(["\'])',
            lambda m: f'{m.group(1)}{cache_busting_version}{m.group(3)}',
            version_text,
            count=1,
        )
    else:
        updated_version_text = f'{version_text.rstrip()}\n__version__ = "{cache_busting_version}"\n'

    version_file.write_text(updated_version_text)
    return cache_busting_version


def _get_static_version_cache_bust(
    pyproject_text: str,
    pyproject_path: Path,
    timestamp: str,
    base_version: str,
) -> str:
    """Handle cache-busting for static version projects."""
    version_pattern = re.compile(
        r'^(version\s*=\s*["\'])([^"\']+)(["\'])',
        re.MULTILINE,
    )
    match = version_pattern.search(pyproject_text)

    if match:
        base_version = match.group(2)
        cache_busting_version = f'{base_version}.post{timestamp}'
        updated_pyproject = version_pattern.sub(
            lambda m: f'{m.group(1)}{cache_busting_version}{m.group(3)}',
            pyproject_text,
            count=1,
        )
        pyproject_path.write_text(updated_pyproject)
        return cache_busting_version

    if '[project]' in pyproject_text:
        cache_busting_version = f'{base_version}.post{timestamp}'
        pyproject_path.write_text(
            pyproject_text.replace(
                '[project]',
                f'[project]\nversion = "{cache_busting_version}"',
                1,
            ),
        )
        return cache_busting_version

    return f'{base_version}.post{timestamp}'


def _prepare_build_directory(local_path: Path) -> tuple[Path, Path]:
    """Prepare the build directory and return build_root and dist_dir."""
    dist_dir = local_path / 'dist'
    if dist_dir.exists():
        logger.debug('cleaning_dist_directory', path=str(dist_dir))
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)

    temp_dir = Path(tempfile.mkdtemp())
    build_root = temp_dir / local_path.name
    shutil.copytree(local_path, build_root, symlinks=True)

    return build_root, dist_dir


def _build_wheel(build_root: Path) -> Path:
    """Build the wheel and return the path to the built wheel."""
    uv_path = shutil.which('uv')
    if uv_path is None:
        msg = 'uv command not found in PATH'
        raise RuntimeError(msg)

    subprocess.run(  # noqa: S603 - using which() to find uv executable
        [uv_path, 'build', '--wheel', str(build_root)],
        cwd=build_root,
        capture_output=True,
        text=True,
        check=True,
    )

    temp_dist_dir = build_root / 'dist'
    if not temp_dist_dir.exists():
        msg = f'No dist directory found after building wheel at {build_root}'
        raise RuntimeError(msg)

    wheel_candidates = list(temp_dist_dir.glob('*.whl'))
    if not wheel_candidates:
        msg = f'No wheel files found in {temp_dist_dir}'
        raise RuntimeError(msg)

    return max(wheel_candidates, key=lambda path: path.stat().st_mtime)


def _build_wheel_from_local_directory(local_path: Path) -> Path:
    """Build a wheel from a local package directory for UV 0.8+ compatibility."""
    timestamp = datetime.datetime.now(tz=ZoneInfo('UTC')).strftime(
        '%Y%m%d%H%M%S',
    )

    logger.info(
        'building_wheel_for_uv_compatibility',
        path=str(local_path),
        reason='uv_0.8_plus_local_install_fix',
        _display_level=1,
    )

    build_root, dist_dir = _prepare_build_directory(local_path)
    try:
        cache_busting_version = _get_cache_busting_version(
            build_root,
            timestamp,
        )
        latest_wheel = _build_wheel(build_root)

        final_wheel_path = dist_dir / latest_wheel.name
        shutil.copy2(latest_wheel, final_wheel_path)

        logger.info(
            'wheel_built_successfully',
            wheel_path=str(final_wheel_path),
            version=cache_busting_version,
            _display_level=1,
        )
    except subprocess.CalledProcessError as exc:
        logger.exception(
            'wheel_build_failed',
            path=str(local_path),
            returncode=exc.returncode,
            stdout=exc.stdout,
            stderr=exc.stderr,
        )
        msg = f'Failed to build wheel from {local_path}: {exc.stderr}'
        raise RuntimeError(msg) from exc
    else:
        return final_wheel_path
    finally:
        # Clean up temporary directory
        shutil.rmtree(build_root.parent, ignore_errors=True)


def get_site_packages_path(
    install_spec: str,
    *,
    force_reinstall: bool = False,
    expected_package: str,
) -> tuple[Path, str, Path]:
    """Get the site-packages directory for a uvx installation.

    Args:
        install_spec: The package specification to install (e.g., git+https://...)
        force_reinstall: Whether to force reinstall the package
        expected_package: The module name to match for dist-info (required)

    Returns:
        Tuple of (site_packages_path, dist_info_name_if_found)

    Raises:
        RuntimeError: If uvx installation fails
    """
    logger.debug(
        'getting_site_packages_path',
        install_spec=install_spec,
        force_reinstall=force_reinstall,
        expected_package=expected_package,
    )

    # For UV 0.8+ compatibility: If this is a local directory, build a wheel first
    # This ensures all files (including non-Python resources) are properly included
    original_install_spec = install_spec
    built_from_local = False
    local_path = Path(install_spec)
    logger.debug(
        'checking_local_wheel_build_conditions',
        install_spec=install_spec,
        path=str(local_path),
        is_absolute=local_path.is_absolute(),
        is_dir=local_path.is_dir(),
        has_pyproject=(local_path / 'pyproject.toml').exists() if local_path.exists() else False,
    )
    if local_path.is_absolute() and local_path.is_dir() and (local_path / 'pyproject.toml').exists():
        logger.info(
            'detected_local_directory_install',
            path=str(local_path),
            action='building_wheel_for_compatibility',
            _display_level=1,
        )

        wheel_path = _build_wheel_from_local_directory(local_path)
        install_spec = str(wheel_path)
        built_from_local = True

        logger.info(
            'using_wheel_instead_of_directory',
            original=original_install_spec,
            wheel=install_spec,
            _display_level=1,
        )

    # Force reinstall when we built from local directory to ensure fresh installation
    if built_from_local:
        force_reinstall = True
        logger.debug(
            'forcing_reinstall_for_local_wheel',
            reason='ensure_fresh_installation_from_local_changes',
        )

    cmd = _build_site_packages_command(
        install_spec,
        force_reinstall=force_reinstall,
    )
    result = _run_uvx_subprocess(cmd)

    if result.returncode != 0:
        logger.error(
            'uvx_get_site_packages_failed',
            stderr=result.stderr,
            stdout=result.stdout,
        )
        msg = f'Failed to get site-packages path with uvx: {result.stderr}'
        raise RuntimeError(msg)

    site_packages = Path(result.stdout.strip())
    dist_info_name, dist_info_path = _extract_dist_info_path(
        result.stderr,
        expected_package,
    )

    logger.debug(
        'uvx_site_packages_found',
        path=str(site_packages),
        dist_info_name=dist_info_name,
        dist_info_path=str(dist_info_path),
    )
    return site_packages, dist_info_name, dist_info_path


def refresh_package(package_name: str, from_path: Path) -> bool:
    """Refresh a package in uvx cache.

    Uses a minimal Python command to trigger the refresh without relying on
    CLI-specific implementations like --help.

    Args:
        package_name: Name of the package to refresh
        from_path: Local path to install from

    Returns:
        True if refresh was successful, False otherwise
    """
    cmd = [
        'uvx',
        '--refresh-package',
        package_name,
        '--from',
        str(from_path),
        'python',
        '-c',
        'print("installed")',  # Simple command to trigger installation
    ]

    result = _run_uvx_subprocess(cmd)

    return result.returncode == 0
