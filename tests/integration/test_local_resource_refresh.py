from __future__ import annotations

import time
from pathlib import Path

from tests.integration.conftest import CliCommand


def _write_pyproject(pkg_dir: Path, package_name: str) -> None:
    pyproject = f"""[project]
name = "{package_name}"
version = "0.0.0"
description = "Package used to verify resource cache busting"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
include = [
    "{package_name}/**"
]
"""
    (pkg_dir / 'pyproject.toml').write_text(pyproject)


def _write_config(workspace: Path, package_name: str, pkg_dir: Path) -> Path:
    config = f"""python-packages:
  {package_name}:
    from: {pkg_dir}
    directory: resources
"""
    config_path = workspace / 'pkglink.config.yaml'
    config_path.write_text(config)
    return config_path


def _create_package(tmp_path: Path, package_name: str) -> tuple[Path, Path]:
    pkg_dir = tmp_path / package_name
    package_root = pkg_dir / package_name
    resources_dir = package_root / 'resources' / 'templates'

    package_root.mkdir(parents=True)
    resources_dir.mkdir(parents=True)
    (package_root / '__init__.py').write_text('__all__ = ()\n')

    resource_file = resources_dir / 'docs-deploy.yaml'
    resource_file.write_text('# version 1\n')

    _write_pyproject(pkg_dir, package_name)

    return pkg_dir, resource_file


def test_local_resource_sync_refreshes_after_update(
    tmp_path: Path,
    run_pkglink_batch: CliCommand,
):
    package_name = 'codeguide'
    pkg_dir, source_resource = _create_package(tmp_path, package_name)
    config_path = _write_config(tmp_path, package_name, pkg_dir)

    first_result = run_pkglink_batch(['--config', str(config_path)], tmp_path)
    assert first_result.returncode == 0, first_result.all_output

    target_resource = tmp_path / '.pkglink' / f'.{package_name}' / 'templates' / 'docs-deploy.yaml'
    assert target_resource.exists()
    assert target_resource.read_text() == '# version 1\n'

    source_resource.write_text('# version 2\n')
    time.sleep(1)

    second_result = run_pkglink_batch(['--config', str(config_path)], tmp_path)
    assert second_result.returncode == 0, second_result.all_output
    assert target_resource.read_text() == '# version 2\n'
