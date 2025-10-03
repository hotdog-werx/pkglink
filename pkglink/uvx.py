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
