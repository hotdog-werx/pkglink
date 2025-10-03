from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from pkglink.batch_config import DEFAULT_CONFIG_FILENAME, PkglinkConfigError, load_batch_contexts


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    return tmp_path / DEFAULT_CONFIG_FILENAME


def write_config(path: Path, content: str) -> None:
    path.write_text(dedent(content).lstrip())


def test_load_batch_contexts_with_defaults(config_path: Path) -> None:
    write_config(
        config_path,
        "\n".join(
            [
                "defaults:",
                "  inside_pkglink: true",
                "  directory: alt-resources",
                "  skip_resources: true",
                "  verbose: 2",
                "",
                "targets:",
                "  - name: integration",
                "    source: github:example/integration",
                "    symlink_name: .integration",
                "    project_name: pkglink-integration",
                "",
                "  - name: tbelt",
                "    source: github:example/toolbelt",
                "    from: tbelt",
                "    use_pkglink_dir: false",
                "    skip_resources: false",
                "    dry_run: true",
                "",
            ],
        ),
    )

    contexts = load_batch_contexts(config_path=config_path)

    assert [getattr(ctx.cli_args, 'entry_name') for ctx in contexts] == [
        "integration",
        "tbelt",
    ]

    first, second = contexts

    assert first.cli_args.directory == 'alt-resources'
    assert first.inside_pkglink is True
    assert first.skip_resources is True
    assert first.cli_args.verbose == 2
    assert first.cli_args.dry_run is False
    assert first.install_spec.name == 'integration'
    assert first.cli_args.source.raw == 'github:example/integration'
    assert first.cli_args.symlink_name == '.integration'
    assert first.cli_args.project_name == 'pkglink-integration'

    assert second.inside_pkglink is False
    assert second.skip_resources is False
    assert second.cli_args.dry_run is True
    assert second.install_spec.name == 'tbelt'
    assert second.module_name == 'toolbelt'
    assert second.cli_args.source.raw == 'github:example/toolbelt'
    assert second.cli_args.from_package is not None
    assert second.cli_args.from_package.raw == 'tbelt'
    assert second.cli_args.project_name is None


@pytest.mark.parametrize(
    "content",
    [
        "targets:\n  - name: missing-source",
        "defaults:\n  inside_pkglink: maybe\n\ntargets:\n  - name: nope\n    source: file:./pkg",
    ],
)
def test_load_batch_contexts_invalid_config(config_path: Path, content: str) -> None:
    write_config(config_path, content)

    with pytest.raises(PkglinkConfigError):
        load_batch_contexts(config_path=config_path)


def test_missing_config_file(tmp_path: Path) -> None:
    with pytest.raises(PkglinkConfigError):
        load_batch_contexts(config_path=tmp_path / DEFAULT_CONFIG_FILENAME)
