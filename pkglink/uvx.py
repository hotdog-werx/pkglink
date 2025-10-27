"""Module for interacting with uvx (uv's tool runner)."""

import datetime
import os
import re
import shutil
import subprocess
import tempfile
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


def _build_wheel_from_local_directory(local_path: Path) -> Path:
    """Build a wheel from a local package directory for UV 0.8+ compatibility."""
    timestamp = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')

    try:
        logger.info(
            'building_wheel_for_uv_compatibility',
            path=str(local_path),
            reason='uv_0.8_plus_local_install_fix',
            _display_level=1,
        )

        dist_dir = local_path / 'dist'
        if dist_dir.exists():
            logger.debug('cleaning_dist_directory', path=str(dist_dir))
            shutil.rmtree(dist_dir)
        dist_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            build_root = Path(temp_dir) / local_path.name
            shutil.copytree(local_path, build_root, symlinks=True)

            pyproject_path = build_root / 'pyproject.toml'
            base_version = '0.0.0'
            cache_busting_version = None

            if pyproject_path.exists():
                pyproject_text = pyproject_path.read_text()
                version_pattern = re.compile(
                    r'^(version\s*=\s*["\"])([^"\
]+)(["\"])',
                    re.MULTILINE,
                )
                match = version_pattern.search(pyproject_text)

                if match:
                    base_version = match.group(2)
                    cache_busting_version = f'{base_version}.post{timestamp}'
                    pyproject_text = version_pattern.sub(
                        lambda m: f'{m.group(1)}{cache_busting_version}{m.group(3)}',
                        pyproject_text,
                        count=1,
                    )
                    pyproject_path.write_text(pyproject_text)
                elif '[project]' in pyproject_text:
                    cache_busting_version = f'{base_version}.post{timestamp}'
                    pyproject_path.write_text(
                        pyproject_text.replace(
                            '[project]',
                            f'[project]\nversion = "{cache_busting_version}"',
                            1,
                        ),
                    )

            if cache_busting_version is None:
                cache_busting_version = f'{base_version}.post{timestamp}'
                logger.debug(
                    'cache_busting_version_fallback',
                    path=str(pyproject_path),
                    version=cache_busting_version,
                )

            subprocess.run(  # noqa: S603 - executing trusted build backend
                ['uv', 'build', '--wheel', str(build_root)],
                cwd=build_root,
                capture_output=True,
                text=True,
                check=True,
            )

            temp_dist_dir = build_root / 'dist'
            if not temp_dist_dir.exists():
                raise RuntimeError(
                    f'No dist directory found after building wheel at {build_root}',
                )

            wheel_candidates = list(temp_dist_dir.glob('*.whl'))
            if not wheel_candidates:
                raise RuntimeError(f'No wheel files found in {temp_dist_dir}')

            latest_wheel = max(
                wheel_candidates,
                key=lambda path: path.stat().st_mtime,
            )
            final_wheel_path = dist_dir / latest_wheel.name
            shutil.copy2(latest_wheel, final_wheel_path)

        logger.info(
            'wheel_built_successfully',
            wheel_path=str(final_wheel_path),
            version=cache_busting_version,
            _display_level=1,
        )
        return final_wheel_path

    except subprocess.CalledProcessError as exc:
        logger.error(
            'wheel_build_failed',
            path=str(local_path),
            returncode=exc.returncode,
            stdout=exc.stdout,
            stderr=exc.stderr,
        )
        raise RuntimeError(
            f'Failed to build wheel from {local_path}: {exc.stderr}',
        ) from exc


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
