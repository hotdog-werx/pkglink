from pathlib import Path
from textwrap import dedent

import pytest

from .conftest import CliCommand, assert_exists_and_type


@pytest.fixture
def pkglink_config_template(tmp_path: Path) -> Path:
    config = tmp_path / 'pkglink.config.yaml'
    config.write_text(
        dedent(
            """
            defaults:
              inside_pkglink: true
              skip_resources: false
              verbose: 2

            github:
              hotdog-werx/pkglink-integration-pkg:
                version: v0.0.1
                project_name: pkglink-integration-pkg
                symlink_name: .pkglink-integration

              hotdog-werx/codeguide:
                version: master
                symlink_name: .codeguide-resources
                inside_pkglink: false
            """,
        ),
    )
    return config


def test_pkglink_batch_executes_entries(
    tmp_path: Path,
    run_pkglink_batch: CliCommand,
    pkglink_config_template: Path,
) -> None:
    project_dir = tmp_path / 'project'
    project_dir.mkdir()

    # copy pkglink.config.yaml into project directory
    config_path = project_dir / 'pkglink.config.yaml'
    config_path.write_text(pkglink_config_template.read_text())

    result = run_pkglink_batch(['-v'], project_dir)
    assert result.returncode == 0

    pkglink_dir = project_dir / '.pkglink'
    assert_exists_and_type(pkglink_dir)

    uvx_target = pkglink_dir / 'pkglink-integration-pkg'
    assert_exists_and_type(uvx_target)
    assert_exists_and_type(uvx_target / 'pyproject.toml')
    assert_exists_and_type(uvx_target / '.pkglink-metadata.yaml')
    assert_exists_and_type(uvx_target / 'src' / 'pkglink_integration_pkg')

    uvx_symlink = pkglink_dir / '.pkglink-integration'
    assert_exists_and_type(uvx_symlink)

    # Codeguide should be installed at root (inside_pkglink: false)
    resource_symlink = project_dir / '.codeguide-resources'
    assert_exists_and_type(resource_symlink)

    # Post-install symlinks from pkglink-integration-pkg should land at project root
    assert_exists_and_type(project_dir / 'index.html')
    assert_exists_and_type(project_dir / 'theme' / 'inner' / 'style.css')

    assert 'download_phase_start' in result.all_output
    assert 'planning_phase_complete' in result.all_output
    assert 'execution_phase_complete' in result.all_output


def test_pkglink_batch_download_failure_stops_execution(
    tmp_path: Path,
    run_pkglink_batch: CliCommand,
) -> None:
    project_dir = tmp_path / 'broken'
    project_dir.mkdir()

    (project_dir / 'pkglink.config.yaml').write_text(
        dedent(
            """
            defaults:
              inside_pkglink: true

            github:
              hotdog-werx/pkglink-integration-pkg:
                version: v0.0.1
                project_name: pkglink-integration-pkg

              hotdog-werx/does-not-exist:
                version: v0.0.1
                inside_pkglink: false
            """,
        ),
    )

    result = run_pkglink_batch(['-v'], project_dir)
    assert result.returncode == 1
    assert 'download_entry_start' in result.all_output
    assert 'configuration_error' not in result.all_output
    # Ensure we never reach planning phase for the failing entry
    assert 'planning_phase_complete' not in result.all_output
