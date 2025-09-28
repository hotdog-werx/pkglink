from dataclasses import dataclass
from pathlib import Path

import pytest

from .conftest import CliCommand, assert_contains_all


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
            args=['some-source', '/some/abs/path'],
            expected_message='Target directory must be relative path, not absolute: /some/abs/path',
        ),
        PkgLinkErrorCase(
            name='pkglink_invalid_github_source',
            args=['github:org'],
            expected_message='Invalid Github source format: github:org',
        ),
        PkgLinkErrorCase(
            name='pkglink_invalid_github_source_empty',
            args=['github: /repo'],
            expected_message='Invalid Github source format: github: /repo',
        ),
        PkgLinkErrorCase(
            name='pkglink_invalid_package',
            args=['@1.2.3'],
            expected_message='Invalid pypi package source format: @1.2.3',
        ),
    ],
    ids=lambda case: case.name,
)
def test_pkglink_argparse_error_cases(
    tmp_path: Path,
    run_pkglink: CliCommand,
    errcase: PkgLinkErrorCase,
):
    test_dir = tmp_path / 'pkglink_arg_parse_error_cases'
    test_dir.mkdir()

    result = run_pkglink(errcase.args, test_dir)
    assert result.returncode == 2
    snippets = [
        'usage: pkglink',
        'pkglink: error:',
        errcase.expected_message,
    ]
    assert_contains_all(result.stderr, snippets, errcase.name)
