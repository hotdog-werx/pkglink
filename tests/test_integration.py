"""Integration tests for pkglink using real toolbelt package."""

import sys
from pathlib import Path
from textwrap import dedent

import pytest
from pytest_mock import MockerFixture

from pkglink.main import main as main_function


def mypkg_test_package(tmp_path: Path) -> Path:
    """Fixture to create a minimal 'mypkg' package structure in tmp_path and return the temp dir."""
    pkg_dir = tmp_path / 'mypkg'
    pkg_dir.mkdir()
    (pkg_dir / '__init__.py').write_text("VERSION = '0.1.0'")
    resources_dir = pkg_dir / 'resources'
    resources_dir.mkdir()
    (resources_dir / 'hello.md').write_text('hello world')
    (tmp_path / 'pyproject.toml').write_text(
        dedent("""
        [project]
        name = "mypkg"
        version = "0.1.0"

        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"

        [tool.hatch.build]
        include = [
        "mypkg/**",
        ]
        """),
    )
    return tmp_path


@pytest.fixture
def mypkg_package(tmp_path: Path) -> Path:
    """Pytest fixture for the minimal mypkg package, returns the temp dir."""
    return mypkg_test_package(tmp_path)


def debug_caplog_streams(
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture,
    label: str = '',
) -> None:
    sys.stdout.write(f'\nCaptured pkglink logs{label}:\n')
    sys.stdout.write(caplog.text)
    captured = capfd.readouterr()
    sys.stdout.write(f'\nCaptured stdout{label}:\n')
    sys.stdout.write(captured.out)
    sys.stdout.write(f'\nCaptured stderr{label}:\n')
    sys.stdout.write(captured.err)


def debug_assertion(
    message: str,
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture,
    label: str = '',
) -> str:
    captured = capfd.readouterr()
    return f'{message}\nLOGS{label}:\n{caplog.text}\nSTDOUT{label}:\n{captured.out}\nSTDERR{label}:\n{captured.err}'


def assert_output_contains(  # noqa: PLR0913 - helper function, gets a pass on params
    output: str,
    substrings: list[str],
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture,
    label: str = '',
    message: str = 'Expected output to contain one of the specified substrings.',
) -> None:
    """Assert that the output contains at least one of the specified substrings."""
    if not any(sub in output for sub in substrings):
        raise AssertionError(
            debug_assertion(
                f'{message}\nChecked for: {substrings}\nOutput:\n{output}',
                caplog,
                capfd,
                label,
            ),
        )


def call_main(
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture,
    label: str = '',
) -> None:
    caplog.set_level('DEBUG')
    try:
        main_function()
    except Exception:
        debug_caplog_streams(caplog, capfd, label)
        raise


def test_pkglink_local_package_real_install(
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    capfd: pytest.CaptureFixture,
    caplog: pytest.LogCaptureFixture,
    mypkg_package: Path,
) -> None:
    """Test real installation of a local package using pkglink."""
    # Change to temp dir
    monkeypatch.chdir(mypkg_package)

    # NOTE: In a real repo, pkglink infers the symlink name from the package name.
    # In this test, since we use --from . (the temp dir), pkglink would use the temp dir name.
    # To ensure the symlink is named .mypkg, we must specify --symlink-name .mypkg explicitly.
    test_args = [
        'pkglink',
        '--from',
        '.',
        'mypkg',
        'resources',
        '--symlink-name',
        '.mypkg',
        '--verbose',
    ]
    mocker.patch.object(sys, 'argv', test_args)

    # Run the CLI main function and capture output
    call_main(caplog, capfd)

    # Check symlink
    symlink = mypkg_package / '.mypkg'
    assert symlink.is_symlink(), debug_assertion(
        f'Symlink {symlink} was not created.',
        caplog,
        capfd,
    )
    # The installed resources dir should contain hello.md
    assert (symlink / 'hello.md').read_text() == 'hello world', debug_assertion(
        "File 'hello.md' was not found or did not contain expected content.",
        caplog,
        capfd,
    )


def test_pkglink_toolbelt_package_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    capfd: pytest.CaptureFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test linking a directory from the real toolbelt package using pkglink."""
    # Change to temp dir
    monkeypatch.chdir(tmp_path)

    # NOTE: This will use the real toolbelt package (should be cached if already installed)
    # Explicitly specify symlink name to ensure .toolbelt is created
    test_args = [
        'pkglink',
        '--from',
        'tbelt',
        'toolbelt',
        'resources',
        '--symlink-name',
        '.toolbelt',
        '--verbose',
    ]
    mocker.patch.object(sys, 'argv', test_args)

    caplog.set_level('DEBUG')
    try:
        main_function()
    except Exception:
        debug_caplog_streams(caplog, capfd)
        raise

    # Check symlink
    symlink = tmp_path / '.toolbelt'
    assert symlink.is_symlink(), debug_assertion(
        f'Symlink {symlink} was not created.',
        caplog,
        capfd,
    )
    # The installed resources dir should contain at least one file
    assert any(symlink.iterdir()), debug_assertion(
        'Toolbelt resources directory should not be empty',
        caplog,
        capfd,
    )

    # Run pkglink again with the same params, should print a message about the symlink already existing
    caplog.clear()
    call_main(caplog, capfd, ' (second run)')
    # Check logs or output for message about symlink already existing
    output = capfd.readouterr().out + caplog.text
    assert_output_contains(
        output,
        ['already exists', 'already a symlink', 'skipping'],
        caplog,
        capfd,
        message='Expected message about symlink already existing',
    )


def test_pkglink_local_package_real_install_force(
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    capfd: pytest.CaptureFixture,
    caplog: pytest.LogCaptureFixture,
    mypkg_package: Path,
) -> None:
    """Test real installation of a local package using pkglink with --force to trigger removal of existing link."""
    # Change to temp dir
    monkeypatch.chdir(mypkg_package)

    # First run: create the symlink
    test_args = [
        'pkglink',
        '--from',
        '.',
        'mypkg',
        'resources',
        '--symlink-name',
        '.mypkg',
        '--verbose',
    ]
    mocker.patch.object(sys, 'argv', test_args)
    call_main(caplog, capfd)
    symlink = mypkg_package / '.mypkg'
    assert symlink.is_symlink()
    assert (symlink / 'hello.md').read_text() == 'hello world'

    # Second run: use --force to trigger removal of the existing link
    caplog.clear()
    test_args_force = [
        'pkglink',
        '--from',
        '.',
        'mypkg',
        'resources',
        '--symlink-name',
        '.mypkg',
        '--force',
        '--verbose',
    ]
    mocker.patch.object(sys, 'argv', test_args_force)
    call_main(caplog, capfd)
    # Check logs for removal message
    output = capfd.readouterr().out + caplog.text
    assert_output_contains(
        output,
        ['removing_existing_target'],
        caplog,
        capfd,
        message='Expected log about removing existing target',
    )
    # Symlink should still exist and be valid
    assert symlink.is_symlink(), debug_assertion(
        f'Symlink {symlink} was not created.',
        caplog,
        capfd,
    )
    assert (symlink / 'hello.md').read_text() == 'hello world', debug_assertion(
        "File 'hello.md' was not found or did not contain expected content.",
        caplog,
        capfd,
    )


def test_pkglink_local_package_real_install_auto_force(
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    capfd: pytest.CaptureFixture,
    caplog: pytest.LogCaptureFixture,
    mypkg_package: Path,
) -> None:
    """Test that pkglink skips symlink recreation for local package installs.

    If the link is already correct (no --force needed).
    """
    # Change to temp dir
    monkeypatch.chdir(mypkg_package)

    # First run: create the symlink
    test_args = [
        'pkglink',
        '--from',
        '.',
        'mypkg',
        'resources',
        '--symlink-name',
        '.mypkg',
        '--verbose',
    ]
    mocker.patch.object(sys, 'argv', test_args)
    call_main(caplog, capfd)
    symlink = mypkg_package / '.mypkg'
    assert symlink.is_symlink()
    assert (symlink / 'hello.md').read_text() == 'hello world'

    # Second run: do NOT use --force, pkglink should skip recreation if the link is already correct
    caplog.clear()
    mocker.patch.object(sys, 'argv', test_args)
    call_main(caplog, capfd)
    # Check logs for skip message
    output = capfd.readouterr().out + caplog.text
    assert_output_contains(
        output,
        [
            'already exists',
            'already a symlink',
            'skipping',
            'target_already_exists_and_correct_skipping',
        ],
        caplog,
        capfd,
        message='Expected message about symlink already existing/skipping',
    )
    # Symlink should still exist and be valid
    assert symlink.is_symlink()
    assert (symlink / 'hello.md').read_text() == 'hello world'


def test_pkglink_local_package_real_install_auto_force_with_conflict(
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    capfd: pytest.CaptureFixture,
    caplog: pytest.LogCaptureFixture,
    mypkg_package: Path,
) -> None:
    """Test that pkglink auto-forces symlink overwrite for local package installs if the target is incorrect."""
    # Change to temp dir
    monkeypatch.chdir(mypkg_package)

    # First run: create the symlink
    test_args = [
        'pkglink',
        '--from',
        '.',
        'mypkg',
        'resources',
        '--symlink-name',
        '.mypkg',
        '--verbose',
    ]
    mocker.patch.object(sys, 'argv', test_args)
    call_main(caplog, capfd)
    symlink = mypkg_package / '.mypkg'
    assert symlink.is_symlink()
    assert (symlink / 'hello.md').read_text() == 'hello world'

    # Replace the symlink with a directory to simulate a conflicting target
    symlink.unlink()
    (mypkg_package / '.mypkg').mkdir()
    (mypkg_package / '.mypkg' / 'dummy.txt').write_text('conflict')

    # Second run: do NOT use --force, pkglink should auto-remove the directory and recreate the symlink
    caplog.clear()
    mocker.patch.object(sys, 'argv', test_args)
    call_main(caplog, capfd)
    # Check logs for removal message
    output = capfd.readouterr().out + caplog.text
    assert_output_contains(
        output,
        ['removing_existing_target'],
        caplog,
        capfd,
        message='Expected log about removing existing target (auto-force for local with conflict)',
    )
    # Symlink should exist and be valid
    assert symlink.is_symlink(), debug_assertion(
        f'Symlink {symlink} was not created.',
        caplog,
        capfd,
    )
    assert (symlink / 'hello.md').read_text() == 'hello world', debug_assertion(
        "File 'hello.md' was not found or did not contain expected content.",
        caplog,
        capfd,
    )
