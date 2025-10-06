from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml
from pytest_mock import MockerFixture

from .conftest import CliCommand, assert_exists_and_type, run_uvx


@dataclass
class PkgLinkExpected:
    module: str
    symlink: str
    project_name: str
    contents: list[str]


@dataclass
class PkgLinkxTestCase:
    name: str
    pkglinkx_args: list[str]
    expect: PkgLinkExpected


@pytest.mark.parametrize(
    'tcase',
    [
        PkgLinkxTestCase(
            name='toolbelt_explicit',
            pkglinkx_args=[
                '--verbose',
                '--from=github:hotdog-werx/toolbelt',
                '--project-name=tbelt',
                'toolbelt',
            ],
            expect=PkgLinkExpected(
                module='toolbelt',
                symlink='.toolbelt',
                project_name='tbelt',
                contents=['presets'],
            ),
        ),
        PkgLinkxTestCase(
            name='toolbelt_no_from',
            pkglinkx_args=[
                'github:hotdog-werx/toolbelt',
                '--project-name=tbelt',
            ],
            expect=PkgLinkExpected(
                module='toolbelt',
                symlink='.toolbelt',
                project_name='tbelt',
                contents=['presets'],
            ),
        ),
        PkgLinkxTestCase(
            name='toolbelt_pypi',
            pkglinkx_args=[
                '--from=tbelt',
                'toolbelt',
            ],
            expect=PkgLinkExpected(
                module='toolbelt',
                symlink='.toolbelt',
                project_name='tbelt',
                contents=['presets'],
            ),
        ),
    ],
    ids=lambda case: case.name,
)
def test_pkglinkx(
    tmp_path: Path,
    run_pkglinkx: CliCommand,
    tcase: PkgLinkxTestCase,
):
    test_dir = tmp_path / f'pkglinkx_case_{tcase.name}'
    test_dir.mkdir()

    result = run_pkglinkx(tcase.pkglinkx_args, test_dir)
    assert result.returncode == 0
    assert 'linked 1 package' in result.stdout

    # Verify .pkglink structure was created
    pkglinkx_dir = test_dir / '.pkglink' / tcase.expect.symlink
    assert_exists_and_type(pkglinkx_dir)

    # Verify expected contents exist in the symlinked directory
    for item in tcase.expect.contents:
        assert_exists_and_type(pkglinkx_dir / item)

    module_dir = test_dir / '.pkglink' / tcase.expect.project_name
    assert_exists_and_type(module_dir)
    assert_exists_and_type(module_dir / 'pyproject.toml')
    assert_exists_and_type(module_dir / '.pkglink-metadata.yaml')
    assert_exists_and_type(module_dir / 'src' / tcase.expect.module)


def test_pkglinkx_dry_run(tmp_path: Path, run_pkglinkx: CliCommand) -> None:
    """Test pkglinkx with --dry-run option."""
    test_dir = tmp_path / 'pkglinkx_dry_run'
    test_dir.mkdir()

    result = run_pkglinkx(
        ['--dry-run', '--from=tbelt', 'toolbelt'],
        test_dir,
    )
    assert result.returncode == 0
    assert 'would link 1 package' in result.stdout

    # Verify no symlink was created
    base_pkglink_dir = test_dir / '.pkglink'
    assert not (base_pkglink_dir / '.toolbelt').exists()
    assert not (base_pkglink_dir / 'tbelt').exists()


def test_pkglinkx_skip_resources(
    tmp_path: Path,
    run_pkglinkx: CliCommand,
) -> None:
    test_dir = tmp_path / 'pkglinkx_dry_run'
    test_dir.mkdir()

    result = run_pkglinkx(
        ['--skip-resources', '--from=tbelt', 'toolbelt'],
        test_dir,
    )
    assert result.returncode == 0
    assert 'linked 1 package' in result.stdout

    # Verify no symlink was created
    base_pkglink_dir = test_dir / '.pkglink'
    assert not (base_pkglink_dir / '.toolbelt').exists()
    assert (base_pkglink_dir / 'tbelt').exists()


def test_pkglinkx_needs_project_name(
    tmp_path: Path,
    run_pkglinkx: CliCommand,
) -> None:
    test_dir = tmp_path / 'pkglink_needs_project_name'
    test_dir.mkdir()

    result = run_pkglinkx(
        ['--dry-run', 'github:hotdog-werx/toolbelt'],
        test_dir,
    )
    assert result.returncode == 1
    assert 'ERROR: cli_operation_failed' in result.stdout
    assert 'you may need to provide --project-name' in result.stdout.replace(
        '\n',
        ' ',
    )


@dataclass
class RepoVersionCase:
    version: str
    expected_output: str


@dataclass
class GithubRepo:
    org: str
    repo: str
    project_name: str | None  # PyPI package name (often underscore version of repo)
    pkg_name: str  # Python package/module name (often underscore version of repo)
    cli_name: str  # CLI command name (often hyphen version of repo)

    def spec(self, version: str) -> str:
        """Get the GitHub install spec as a string for CLI args."""
        return f'github:{self.org}/{self.repo}@{version}'


def test_pkglinkx_switch_back(tmp_path: Path, run_pkglinkx: CliCommand):
    """Test switching back and forth between different versions."""
    test_dir = tmp_path / 'param_case_switch_back'
    test_dir.mkdir()

    repo_name = 'pkglink-integration-pkg'
    spec_1 = [f'github:hotdog-werx/{repo_name}@v0.0.1']
    spec_2 = [f'github:hotdog-werx/{repo_name}@v0.0.2']

    # Install first version
    result = run_pkglinkx(spec_1, test_dir)
    assert result.returncode == 0
    assert 'linked 1 package' in result.stdout

    # Verify .pkglink structure was created
    pkglink_dir = test_dir / '.pkglink' / repo_name
    assert_exists_and_type(pkglink_dir)

    # Verify post-install setup symlinks are created at project root, not inside .pkglink
    assert_exists_and_type(test_dir / 'index.html')
    assert_exists_and_type(test_dir / 'theme' / 'inner' / 'style.css')
    assert not (test_dir / '.pkglink' / 'index.html').exists()
    assert not (test_dir / '.pkglink' / 'theme').exists()

    # Test CLI execution for first version
    cli_result = run_uvx(
        ['--from', str(pkglink_dir), 'test-cli'],
        test_dir,
    )
    assert cli_result.returncode == 0
    assert '"version":"0.0.1"' in cli_result.stdout

    # Run pkglinkx for second version
    result = run_pkglinkx(spec_2, test_dir)
    assert result.returncode == 0
    assert 'linked 1 package' in result.stdout

    # Test CLI execution for second version
    cli_result = run_uvx(
        ['--from', str(pkglink_dir), 'test-cli'],
        test_dir,
    )
    assert cli_result.returncode == 0
    assert '"version":"0.0.2"' in cli_result.stdout

    # Test 3: Switch back to first version to ensure bidirectional switching
    result = run_pkglinkx(spec_1, test_dir)
    assert result.returncode == 0

    # Verify we're back to first version
    cli_result = run_uvx(
        ['--from', str(pkglink_dir), 'test-cli'],
        test_dir,
    )
    assert cli_result.returncode == 0
    assert '"version":"0.0.1"' in cli_result.stdout


def test_pkglinkx_metadata_tracking(tmp_path: Path, run_pkglinkx: CliCommand):
    """Test that pkglinkx properly tracks metadata for version changes."""
    test_dir = tmp_path / 'metadata_test'
    test_dir.mkdir()

    repo_name = 'pkglink-integration-pkg'
    spec_1 = [f'github:hotdog-werx/{repo_name}@v0.0.1']
    spec_2 = [f'github:hotdog-werx/{repo_name}@v0.0.2']

    result = run_pkglinkx(spec_1, test_dir)
    assert result.returncode == 0

    # Check metadata file
    metadata_file = test_dir / '.pkglink' / repo_name / '.pkglink-metadata.yaml'
    assert metadata_file.exists()

    with metadata_file.open() as f:
        metadata = yaml.safe_load(f)

    # Verify metadata structure
    assert 'version' in metadata
    assert 'source_hash' in metadata
    assert 'install_spec' in metadata
    assert 'package_name' in metadata
    assert 'console_scripts' in metadata
    assert 'test-cli' in metadata['console_scripts']

    # Store first hash
    first_hash = metadata['source_hash']

    # Install second version
    result = run_pkglinkx(spec_2, test_dir)
    assert result.returncode == 0

    # Check that metadata was updated
    with metadata_file.open() as f:
        new_metadata = yaml.safe_load(f)

    # Hash should be different for different versions
    assert new_metadata['source_hash'] != first_hash


@dataclass
class PkgLinkxErrorCase:
    name: str
    args: list[str]
    expected_message: str


@pytest.mark.parametrize(
    'errcase',
    [
        PkgLinkxErrorCase(
            name='no_args',
            args=[],
            expected_message='error: the following arguments are required: source',
        ),
        PkgLinkxErrorCase(
            name='bad_args',
            args=['--from-package', 'nonexistentpackage'],
            expected_message='error: unrecognized arguments: --from-package',
        ),
    ],
    ids=lambda case: case.name,
)
def test_pkglinkx_error_cases(
    tmp_path: Path,
    run_pkglinkx: CliCommand,
    errcase: PkgLinkxErrorCase,
):
    test_dir = tmp_path / 'pkglink_error_case'
    test_dir.mkdir()

    result = run_pkglinkx(errcase.args, test_dir)
    assert result.returncode != 0
    if 'usage:' not in result.stderr:
        assert 'ERROR: cli_operation_failed' in result.stderr
    assert errcase.expected_message in result.stderr.replace('\n', ' ')


@pytest.mark.parametrize(
    'supports_symlinks',
    [True, False],
)
def test_pkglinkx_install_twice(
    tmp_path: Path,
    run_pkglinkx: CliCommand,
    mocker: MockerFixture,
    supports_symlinks: bool,  # noqa: FBT001 - this is pass the pytest param
):
    """Test fallback copy logic when symlinks are not supported."""
    test_dir = tmp_path / 'param_case_switch_back'
    test_dir.mkdir()

    repo_name = 'pkglink-integration-pkg'
    spec_1 = [f'github:hotdog-werx/{repo_name}@v0.0.1']

    # Patch supports_symlinks to return False to force fallback copy
    mocker.patch(
        'pkglink.symlinks.supports_symlinks',
        return_value=supports_symlinks,
    )

    # Install first version
    result = run_pkglinkx(spec_1, test_dir)
    assert result.returncode == 0
    assert 'linked 1 package' in result.stdout

    # Verify .pkglink structure was created
    pkglink_dir = test_dir / '.pkglink' / repo_name
    assert_exists_and_type(pkglink_dir)
    # Fallback: should be a directory, not a symlink
    if supports_symlinks:
        assert (pkglink_dir / 'src' / 'pkglink_integration_pkg').is_symlink()
    else:
        assert not (pkglink_dir / 'src' / 'pkglink_integration_pkg').is_symlink()
    assert (pkglink_dir / 'src' / 'pkglink_integration_pkg').is_dir()

    # Install again
    result = run_pkglinkx(spec_1, test_dir)
    assert result.returncode == 0
    assert 'linked 1 package' in result.stdout


def test_pkglinkx_pyproject_dependencies(
    tmp_path: Path,
    run_pkglinkx: CliCommand,
):
    """Test that pyproject.toml for pkglink-integration-pkg includes dependencies."""
    test_dir = tmp_path / 'pyproject_deps_test'
    test_dir.mkdir()

    repo_name = 'pkglink-integration-pkg'
    spec = [f'github:hotdog-werx/{repo_name}@v0.0.1']

    result = run_pkglinkx(spec, test_dir)
    assert result.returncode == 0

    pyproject_file = test_dir / '.pkglink' / repo_name / 'pyproject.toml'
    assert pyproject_file.exists()

    pyproject_text = pyproject_file.read_text()
    # Check for [project] section and dependencies
    assert '[project]' in pyproject_text
    assert 'dependencies' in pyproject_text
    assert 'pydantic' in pyproject_text
