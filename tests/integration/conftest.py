import logging
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture

from pkglink.cli.pkglink import main as pkglink_main
from pkglink.cli.pkglinkx import main as pkglinkx_main


def strip_ansi(text: str) -> str:
    """Remove ANSI color codes from text."""
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def run_uvx(uvx_args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run uvx commands via subprocess for testing."""
    result = subprocess.run(  # noqa: S603 - executing uvx
        ['uvx', *uvx_args],  # noqa: S607 - ensure uvx is explicit
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("RETURN CODE:", result.returncode)
    return result


class Result(BaseModel):
    returncode: int
    stdout: str
    stderr: str
    log: str | None = None

    @property
    def all_output(self) -> str:
        """Combine stdout, stderr, and log for unified output checking."""
        return (self.stdout or '') + (self.stderr or '') + (self.log or '')


@dataclass
class RunCommandContext:
    cli_name: str
    main_func: Callable
    args: list[str]
    cwd: Path
    capsys: pytest.CaptureFixture
    caplog: pytest.LogCaptureFixture
    mocker: MockerFixture


def _run_command(ctx: RunCommandContext) -> Result:
    """Helper for CLI main function execution with pytest fixtures."""
    old_cwd = Path.cwd()
    try:
        os.chdir(ctx.cwd)
        ctx.mocker.patch.object(sys, 'argv', [ctx.cli_name, *ctx.args])
        ctx.caplog.set_level(logging.DEBUG)
        try:
            exit_code = ctx.main_func()
        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 1
        else:
            exit_code = 0
        captured = ctx.capsys.readouterr()
        stdout = strip_ansi(captured.out)
        stderr = strip_ansi(captured.err)
        log_output = strip_ansi(ctx.caplog.text)
        return Result(
            returncode=exit_code,
            stdout=stdout,
            stderr=stderr,
            log=log_output,
        )
    finally:
        os.chdir(old_cwd)


CliCommand = Callable[[list[str], Path], Result]


@pytest.fixture
def run_pkglink(
    capsys: pytest.CaptureFixture,
    caplog: pytest.LogCaptureFixture,
    mocker: MockerFixture,
) -> CliCommand:
    def _run(args: list[str], cwd: Path) -> Result:
        ctx = RunCommandContext(
            cli_name='pkglink',
            main_func=pkglink_main,
            args=args,
            cwd=cwd,
            capsys=capsys,
            caplog=caplog,
            mocker=mocker,
        )
        return _run_command(ctx)

    return _run


@pytest.fixture
def run_pkglinkx(
    capsys: pytest.CaptureFixture,
    caplog: pytest.LogCaptureFixture,
    mocker: MockerFixture,
) -> CliCommand:
    def _run(args: list[str], cwd: Path) -> Result:
        ctx = RunCommandContext(
            cli_name='pkglinkx',
            main_func=pkglinkx_main,
            args=args,
            cwd=cwd,
            capsys=capsys,
            caplog=caplog,
            mocker=mocker,
        )
        return _run_command(ctx)

    return _run


def assert_contains_all(output: str, snippets: list[str], context: str = ''):
    missing = [s for s in snippets if s not in output]
    if missing:
        pytest.fail(
            f'Missing expected snippet(s) in {context}: {missing}\nActual output:\n{output}',
        )


def assert_exists_and_type(target: Path):
    target = target.resolve()
    assert target.exists(), f'Missing expected item: {target}'
    if hasattr(target, 'is_symlink'):
        if target.is_symlink():
            return
        assert target.is_dir() or target.is_file(), f'Expected symlink or copy for {target}'
