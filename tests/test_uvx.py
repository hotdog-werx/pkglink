from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest
    from pytest_mock import MockerFixture

from pkglink.uvx import _run_uvx_subprocess

DUMMY_TOKEN = 'not-a-real-token'  # noqa: S105


def _capture_env(mocker: MockerFixture) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def _fake_run(
        cmd: list[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        captured['env'] = kwargs.get('env')
        return subprocess.CompletedProcess(cmd, 0, '', '')

    mocker.patch('subprocess.run', side_effect=_fake_run)
    return captured


def test_run_uvx_subprocess_uses_pkglink_token(
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_env(mocker)
    monkeypatch.setenv('PKGLINK_GITHUB_TOKEN', DUMMY_TOKEN)
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)

    _run_uvx_subprocess(['uvx', '--version'])

    assert captured['env']['GITHUB_TOKEN'] == DUMMY_TOKEN


def test_run_uvx_subprocess_prefers_pkglink_token(
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_env(mocker)
    monkeypatch.setenv('PKGLINK_GITHUB_TOKEN', DUMMY_TOKEN)
    monkeypatch.setenv('GITHUB_TOKEN', 'fallback-token')

    _run_uvx_subprocess(['uvx', '--version'])

    assert captured['env']['GITHUB_TOKEN'] == DUMMY_TOKEN


def test_run_uvx_subprocess_passes_through_without_token(
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_env(mocker)
    monkeypatch.delenv('PKGLINK_GITHUB_TOKEN', raising=False)
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)

    _run_uvx_subprocess(['uvx', '--version'])

    assert captured['env'] is None


def test_run_uvx_subprocess_inherits_github_token(
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_env(mocker)
    monkeypatch.delenv('PKGLINK_GITHUB_TOKEN', raising=False)
    monkeypatch.setenv('GITHUB_TOKEN', 'inherited-token')

    _run_uvx_subprocess(['uvx', '--version'])

    assert captured['env'] is None
