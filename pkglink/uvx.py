"""Module for interacting with uvx (uv's tool runner)."""

import os
import re
import subprocess
from pathlib import Path

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
    
    # For local wheel installs, --force-reinstall should be sufficient
    # --no-cache causes temp environment cleanup issues
    # if install_spec.endswith('.whl'):
    #     cmd.append('--no-cache')
        
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


def _build_wheel_from_local_directory(local_path: Path) -> Path:
    """Build a wheel from a local package directory for UV 0.8+ compatibility.
    
    Args:
        local_path: Path to the local package directory
        
    Returns:
        Path to the built wheel file
        
    Raises:
        RuntimeError: If building the wheel fails
    """
    import subprocess
    import shutil
    
    try:
        logger.info(
            'building_wheel_for_uv_compatibility',
            path=str(local_path),
            reason='uv_0.8_plus_local_install_fix',
            _display_level=1,
        )
        
        # Clean the dist directory first to ensure fresh build
        dist_dir = local_path / 'dist'
        if dist_dir.exists():
            logger.debug('cleaning_dist_directory', path=str(dist_dir))
            shutil.rmtree(dist_dir)
        
        # Build the wheel using uv build
        subprocess.run(
            ['uv', 'build', '--wheel', str(local_path)],
            cwd=local_path,
            capture_output=True,
            text=True,
            check=True
        )
        
        # Find the built wheel in the dist directory
        if not dist_dir.exists():
            raise RuntimeError(f'No dist directory found after building wheel at {local_path}')
            
        wheel_files = list(dist_dir.glob('*.whl'))
        if not wheel_files:
            raise RuntimeError(f'No wheel files found in {dist_dir}')
            
        # Return the most recent wheel (in case there are multiple)
        wheel_path = max(wheel_files, key=lambda p: p.stat().st_mtime)
        logger.info(
            'wheel_built_successfully',
            wheel_path=str(wheel_path),
            _display_level=1,
        )
        return wheel_path
        
    except subprocess.CalledProcessError as e:
        logger.error(
            'wheel_build_failed',
            path=str(local_path),
            returncode=e.returncode,
            stdout=e.stdout,
            stderr=e.stderr
        )
        raise RuntimeError(f'Failed to build wheel from {local_path}: {e.stderr}') from e


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
    if (local_path.is_absolute() and 
        local_path.is_dir() and 
        (local_path / 'pyproject.toml').exists()):
        
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
            reason='ensure_fresh_installation_from_local_changes'
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
