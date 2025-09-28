import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from .conftest import CliCommand


@dataclass
class PkgLinkTestCase:
    name: str
    pkglink_args: list[str]
    expected_symlink: str
    expected_contents: list[Path]
    expected_from_setup: list[Path] | None = None


@pytest.mark.parametrize(
    'tcase',
    [
        PkgLinkTestCase(
            name='codeguide_basic',
            pkglink_args=[
                'github:hotdog-werx/codeguide',
            ],
            expected_symlink='.codeguide',
            expected_contents=[
                Path('configs'),
                Path('poe'),
                Path('toolbelt'),
            ],
        ),
        PkgLinkTestCase(
            name='codeguide_different_name',
            pkglink_args=[
                '--symlink-name=.mycodeguide',
                'github:hotdog-werx/codeguide',
            ],
            expected_symlink='.mycodeguide',
            expected_contents=[
                Path('configs'),
                Path('poe'),
                Path('toolbelt'),
            ],
        ),
        PkgLinkTestCase(
            name='codeguide_inside_pkglink',
            pkglink_args=[
                'github:hotdog-werx/codeguide',
                '--inside-pkglink',
            ],
            expected_symlink='.codeguide',
            expected_contents=[
                Path('configs'),
                Path('poe'),
                Path('toolbelt'),
            ],
        ),
        PkgLinkTestCase(
            name='codeguide_pin_version',
            pkglink_args=[
                'github:hotdog-werx/codeguide@v0.0.1',
            ],
            expected_symlink='.codeguide',
            expected_contents=[
                Path('configs'),
                Path('poe'),
                Path('toolbelt'),
            ],
        ),
        PkgLinkTestCase(
            name='toolbelt',
            pkglink_args=[
                'github:hotdog-werx/toolbelt',
                '--project-name=tbelt',
            ],
            expected_symlink='.toolbelt',
            expected_contents=[Path('presets')],
        ),
        PkgLinkTestCase(
            name='toolbelt_different_directory_target',
            pkglink_args=[
                '--project-name=tbelt',
                'github:hotdog-werx/toolbelt',
                'config',  # this is a subpackage inside toolbelt
            ],
            expected_symlink='.toolbelt',
            expected_contents=[Path('models.py')],
        ),
        PkgLinkTestCase(
            name='toolbelt_from_pypi',
            pkglink_args=['--from=tbelt', 'toolbelt'],
            expected_symlink='.toolbelt',
            expected_contents=[Path('presets')],
        ),
        PkgLinkTestCase(
            name='toolbelt_from_pypi_version',
            pkglink_args=['--from=tbelt@0.0.3', 'toolbelt'],
            expected_symlink='.toolbelt',
            expected_contents=[Path('presets')],
        ),
        PkgLinkTestCase(
            name='toolbelt_from_pypi_different_name',
            pkglink_args=['--symlink-name=.tbelt', '--from=tbelt', 'toolbelt'],
            expected_symlink='.tbelt',
            expected_contents=[Path('presets')],
        ),
        PkgLinkTestCase(
            name='pkglink_integration_pkg',
            pkglink_args=['github:hotdog-werx/pkglink-integration-pkg'],
            expected_symlink='.pkglink-integration-pkg',
            expected_contents=[
                Path('docs') / 'index.html',
                Path('docs') / 'style.css',
                Path('pkglink.yaml'),
            ],
            expected_from_setup=[
                Path('index.html'),
                Path('theme') / 'inner' / 'style.css',
            ],
        ),
        PkgLinkTestCase(
            name='pkglink_integration_pkg_pinned',
            pkglink_args=['github:hotdog-werx/pkglink-integration-pkg@v0.0.1'],
            expected_symlink='.pkglink-integration-pkg',
            expected_contents=[
                Path('docs') / 'index.html',
                Path('docs') / 'style.css',
                Path('pkglink.yaml'),
            ],
            expected_from_setup=[
                Path('index.html'),
                Path('theme') / 'inner' / 'style.css',
            ],
        ),
        PkgLinkTestCase(
            name='pkglink_integration_pkg_pinned_sha',
            pkglink_args=[
                'github:hotdog-werx/pkglink-integration-pkg@03ab93b2febff4ef5f8c3bc635f3379c2a730bd4',
            ],
            expected_symlink='.pkglink-integration-pkg',
            expected_contents=[
                Path('docs') / 'index.html',
                Path('docs') / 'style.css',
                Path('pkglink.yaml'),
            ],
            expected_from_setup=[
                Path('index.html'),
                Path('theme') / 'inner' / 'style.css',
            ],
        ),
        PkgLinkTestCase(
            name='local-integration-absolute',
            pkglink_args=[str(Path.cwd() / 'local-integration')],
            expected_symlink='.local-integration',
            expected_contents=[
                Path('docs') / 'index.html',
                Path('docs') / 'style.css',
                Path('pkglink.yaml'),
            ],
            expected_from_setup=[
                Path('index.html'),
                Path('theme') / 'inner' / 'style.css',
            ],
        ),
        PkgLinkTestCase(
            name='local-integration-relative',
            pkglink_args=['./local-integration'],
            expected_symlink='.local-integration',
            expected_contents=[
                Path('docs') / 'index.html',
                Path('docs') / 'style.css',
                Path('pkglink.yaml'),
            ],
            expected_from_setup=[
                Path('index.html'),
                Path('theme') / 'inner' / 'style.css',
            ],
        ),
    ],
    ids=lambda case: case.name,
)
def test_pkglink(
    tmp_path: Path,
    run_pkglink: CliCommand,
    tcase: PkgLinkTestCase,
):
    test_dir = tmp_path / f'pkglink_case_{tcase.name}'
    test_dir.mkdir()

    if './local-integration' in tcase.pkglink_args:
        # copy local-integration to a temp dir to simulate a local path
        local_integration_src = Path.cwd() / 'local-integration'
        local_integration_dst = test_dir / 'local-integration'
        shutil.copytree(local_integration_src, local_integration_dst)

    result = run_pkglink(tcase.pkglink_args, test_dir)
    assert result.returncode == 0
    assert 'pkglink_completed' in result.stdout

    # Verify .pkglink structure was created
    pkglink_dir = (
        test_dir / tcase.expected_symlink
        if '--inside-pkglink' not in tcase.pkglink_args
        else test_dir / '.pkglink' / tcase.expected_symlink
    )

    # Verify expected contents exist in the symlinked directory
    for item in tcase.expected_contents:
        assert (pkglink_dir / Path(item)).exists()

    if tcase.expected_from_setup is not None:
        for item in tcase.expected_from_setup:
            assert (test_dir / Path(item)).exists()


def test_pkglink_dry_run(tmp_path: Path, run_pkglink: CliCommand) -> None:
    test_dir = tmp_path / 'pkglink_dry_run'
    test_dir.mkdir()

    result = run_pkglink(
        ['--dry-run', 'github:hotdog-werx/codeguide'],
        test_dir,
    )
    assert result.returncode == 0
    assert 'dry_run_plan_complete' in result.stdout

    # Verify no symlink was created
    pkglink_dir = test_dir / '.codeguide'
    assert not pkglink_dir.exists()


def test_pkglink_new_name(tmp_path: Path, run_pkglink: CliCommand) -> None:
    test_dir = tmp_path / 'pkglink_dry_run'
    test_dir.mkdir()

    result = run_pkglink(
        ['--symlink-name=.mycodeguide', 'github:hotdog-werx/codeguide'],
        test_dir,
    )
    assert result.returncode == 0
    assert 'pkglink_completed' in result.stdout

    # Verify no symlink was created
    pkglink_dir = test_dir / '.codeguide'
    assert not pkglink_dir.exists()


@dataclass
class PkgLinkErrorCase:
    name: str
    args: list[str]
    expected_message: str


@pytest.mark.parametrize(
    'errcase',
    [
        PkgLinkErrorCase(
            name='invalid_resource_directory',
            args=['github:hotdog-werx/codeguide', 'nodir'],
            expected_message='Resource directory not found:',
        ),
        PkgLinkErrorCase(
            name='pkglink_invalid_repo',
            args=['github:hotdog-werx/invalid-repo'],
            expected_message='404 Not Found',
        ),
    ],
    ids=lambda case: case.name,
)
def test_pkglink_error_cases(
    tmp_path: Path,
    run_pkglink: CliCommand,
    errcase: PkgLinkErrorCase,
):
    test_dir = tmp_path / 'pkglink_error_case'
    test_dir.mkdir()

    result = run_pkglink(errcase.args, test_dir)
    assert result.returncode == 1
    assert '[EXCEPTION] cli_operation_failed' in result.stdout
    assert errcase.expected_message in result.stdout.replace('\n', ' ')


def test_pkglink_self_link(tmp_path: Path, run_pkglink: CliCommand) -> None:
    """Test pkglink linking to itself."""
    test_dir = tmp_path / 'pkglink_self_link'
    test_dir.mkdir()

    # copy local-integration to a temp dir to simulate a local path
    local_integration_src = Path.cwd() / 'local-integration'
    local_integration_dst = test_dir / 'local-integration'
    shutil.copytree(local_integration_src, local_integration_dst)

    result = run_pkglink(['.'], local_integration_dst)
    assert result.returncode == 0
    assert 'pkglink_completed' in result.stdout

    # Verify no symlink was created
    link_dir = local_integration_dst / '.local-integration'
    assert link_dir.exists()
    assert (link_dir / 'docs' / 'index.html').exists()
    assert (link_dir / 'docs' / 'style.css').exists()
    assert (local_integration_dst / 'index.html').exists()
    assert (local_integration_dst / 'theme' / 'inner' / 'style.css').exists()
