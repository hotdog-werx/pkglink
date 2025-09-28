from pathlib import Path

from .conftest import CliCommand, assert_contains_all

INTEGRATION_DIR: Path = Path.cwd() / 'local-integration-diff'


def test_local_install_default(
    tmp_path: Path,
    run_pkglinkx: CliCommand,
) -> None:
    test_dir: Path = tmp_path / 'local_default'
    test_dir.mkdir()
    result = run_pkglinkx([str(INTEGRATION_DIR)], test_dir)
    assert result.returncode != 0
    step1_snippets = [
        'Could not find dist-info for expected package',
        'provide --project-name matching the PyPI/project name',
        'python_project-0.0.2.dist-info',
    ]
    assert_contains_all(result.all_output, step1_snippets, 'default install')


def test_local_install_with_project_name(
    tmp_path: Path,
    run_pkglinkx: CliCommand,
) -> None:
    test_dir: Path = tmp_path / 'local_project_name'
    test_dir.mkdir()
    result = run_pkglinkx(
        ['--project-name=python-project', str(INTEGRATION_DIR)],
        test_dir,
    )
    assert result.returncode != 0
    step2_snippets = [
        'package_root_not_found',
        'use of --from may be needed to specify correct module',
        'no_package_subdir_found_skipping_resource_symlink',
        'FileNotFoundError: Source does not exist:',
    ]
    assert_contains_all(
        result.all_output,
        step2_snippets,
        'project name install',
    )


def test_local_install_with_from_module_name(
    tmp_path: Path,
    run_pkglinkx: CliCommand,
) -> None:
    test_dir: Path = tmp_path / 'local_from_module_name'
    test_dir.mkdir()
    result = run_pkglinkx(
        [
            '--project-name=python-project',
            f'--from={INTEGRATION_DIR!s}',
            'module_name',
        ],
        test_dir,
    )
    assert result.returncode == 0
    step3_snippets = [
        'no_package_subdir_found_skipping_resource_symlink',
        'use of --from may be needed to specify correct module',
        'next_steps',
    ]
    assert_contains_all(
        result.all_output,
        step3_snippets,
        'from module_name install',
    )


def test_local_install_with_from_module_name_utils(
    tmp_path: Path,
    run_pkglinkx: CliCommand,
) -> None:
    test_dir: Path = tmp_path / 'local_from_module_name_utils'
    test_dir.mkdir()
    result = run_pkglinkx(
        [
            '--project-name=python-project',
            f'--from={INTEGRATION_DIR!s}',
            'module_name',
            'utils',
        ],
        test_dir,
    )
    assert result.returncode == 0
    assert 'success' in (result.stdout or '').lower() or 'linked' in (result.stdout or '').lower()
    pkglink_dir = test_dir / '.pkglink' / 'python-project'
    assert pkglink_dir.exists()
    assert pkglink_dir.is_dir()
    assert (pkglink_dir / 'pyproject.toml').exists()
    assert (pkglink_dir / '.pkglink-metadata.yaml').exists()
    src_dir = pkglink_dir / 'src'
    assert src_dir.exists()
    assert src_dir.is_dir()
    assert (src_dir / 'module_name').exists()
    assert (src_dir / 'module_name' / 'utils').exists()
    local_dir = test_dir / '.pkglink' / '.local-integration-diff'
    assert local_dir.exists()
    assert local_dir.is_dir()
    assert (local_dir / 'helper.md').exists()
