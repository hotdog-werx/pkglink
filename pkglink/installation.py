"""UV package installation utilities."""

import subprocess
import tempfile
from pathlib import Path

from pkglink.models import SourceSpec
from pkglink.parsing import build_uv_install_spec


def install_with_uv(spec: SourceSpec) -> Path:
    """Install package using UV and return installation path."""
    if spec.source_type == 'local':
        msg = 'Cannot install local source with UV'
        raise ValueError(msg)

    temp_dir = Path(tempfile.mkdtemp(prefix='pkglink_'))
    install_spec = build_uv_install_spec(spec)

    try:
        subprocess.run(
            ['uv', 'pip', 'install', install_spec, '--target', str(temp_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        msg = f'UV installation failed: {e.stderr}'
        raise RuntimeError(msg) from e

    return temp_dir


def find_exact_match(install_dir: Path, expected_name: str) -> Path | None:
    """Strategy 1: Look for exact name match."""
    exact_match = install_dir / expected_name
    return exact_match if exact_match.exists() and exact_match.is_dir() else None


def find_python_package(install_dir: Path) -> Path | None:
    """Strategy 2: Look for directories with __init__.py."""
    for item in install_dir.iterdir():
        if item.is_dir() and (item / '__init__.py').exists():
            return item
    return None


def find_with_resources(install_dir: Path) -> Path | None:
    """Strategy 3: Find directories containing 'resources' folder."""
    for item in install_dir.iterdir():
        if item.is_dir() and any(subdir.name == 'resources' for subdir in item.iterdir() if subdir.is_dir()):
            return item
    return None


def find_first_directory(install_dir: Path) -> Path | None:
    """Strategy 4: Return the first directory found."""
    for item in install_dir.iterdir():
        if item.is_dir():
            return item
    return None


def find_package_root(install_dir: Path, expected_name: str) -> Path:
    """Find the actual package directory after UV installation."""
    strategies = [
        lambda: find_exact_match(install_dir, expected_name),
        lambda: find_python_package(install_dir),
        lambda: find_with_resources(install_dir),
        lambda: find_first_directory(install_dir),
    ]

    for strategy in strategies:
        result = strategy()
        if result:
            return result

    msg = f'Could not locate package in {install_dir}'
    raise FileNotFoundError(msg)


def resolve_source_path(spec: SourceSpec) -> Path:
    """Resolve source specification to local filesystem path."""
    if spec.source_type == 'local':
        return Path(spec.name).expanduser().resolve()

    # Install with UV and find package root
    install_dir = install_with_uv(spec)
    return find_package_root(install_dir, spec.name)
