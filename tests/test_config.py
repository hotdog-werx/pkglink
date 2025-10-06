from pathlib import Path
from textwrap import dedent

import pytest

from pkglink.config import (
    DEFAULT_CONFIG_FILENAME,
    PkglinkConfig,
    PkglinkConfigError,
    build_contexts,
    load_config,
    load_contexts,
)


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    return tmp_path / DEFAULT_CONFIG_FILENAME


def write_config(path: Path, content: str) -> None:
    path.write_text(dedent(content).lstrip())


def test_load_contexts_merges_defaults(config_path: Path) -> None:
    write_config(
        config_path,
        """
        defaults:
          inside_pkglink: true
          directory: alt-resources
          skip_resources: true
          verbose: 2

        github:
          example/integration:
            symlink_name: .integration
            project_name: pkglink-integration

          example/toolbelt:
            from: tbelt
            inside_pkglink: false
            skip_resources: false
            dry_run: true
        """,
    )

    contexts = load_contexts(config_path=config_path)

    assert [ctx.entry_name or ctx.get_display_name() for ctx in contexts] == [
        'integration',
        'toolbelt',
    ]

    first, second = contexts

    assert first.cli_args.directory == 'alt-resources'
    assert first.inside_pkglink is True
    assert first.skip_resources is True
    assert first.cli_args.verbose == 2
    assert first.cli_args.dry_run is False
    assert first.install_spec.name == 'integration'
    assert first.cli_args.source.raw == 'github:example/integration@master'
    assert first.cli_args.symlink_name == '.integration'
    assert first.cli_args.project_name == 'pkglink-integration'

    assert second.inside_pkglink is False
    assert second.skip_resources is False
    assert second.cli_args.dry_run is True
    assert second.install_spec.name == 'tbelt'
    assert second.module_name == 'toolbelt'
    assert second.cli_args.source.raw == 'github:example/toolbelt@master'
    assert second.cli_args.from_package is not None
    assert second.cli_args.from_package.raw == 'tbelt'
    assert second.cli_args.project_name is None

    config, normalized_links = load_config(config_path)
    assert isinstance(config, PkglinkConfig)
    assert set(normalized_links.keys()) == {'integration', 'toolbelt'}


@pytest.mark.parametrize(
    'content',
    [
        'github:\n  missing_source: {}',
        'defaults:\n  inside_pkglink: "maybe"\n\ngithub:\n  "example/nope": {}',
    ],
)
def test_load_config_invalid_values(config_path: Path, content: str) -> None:
    write_config(config_path, content)

    with pytest.raises(PkglinkConfigError):
        load_config(config_path)


def test_missing_config_file(tmp_path: Path) -> None:
    with pytest.raises(PkglinkConfigError):
        load_config(tmp_path / DEFAULT_CONFIG_FILENAME)


def test_invalid_yaml_raises(config_path: Path) -> None:
    config_path.write_text('links: [invalid')

    with pytest.raises(PkglinkConfigError):
        load_config(config_path)


def test_build_contexts_accepts_loaded_config(config_path: Path) -> None:
    write_config(
        config_path,
        """
        github:
          example/integration: master
        """,
    )

    config, normalized_links = load_config(config_path)
    contexts = build_contexts(config, normalized_links, config_path=config_path)
    assert len(contexts) == 1
    assert contexts[0].entry_name == 'integration'


def test_duplicate_project_names_raise(config_path: Path) -> None:
    write_config(
        config_path,
        """
                github:
                    example/first:
                        project_name: shared-project
                    example/second:
                        project_name: shared-project
                """,
    )

    with pytest.raises(PkglinkConfigError) as excinfo:
        load_contexts(config_path=config_path)

    message = str(excinfo.value)
    assert 'project_name conflicts' in message
    assert "'shared-project'" in message
    assert 'first' in message
    assert 'second' in message


def test_duplicate_symlink_names_raise(config_path: Path) -> None:
    write_config(
        config_path,
        """
                github:
                    example/alpha:
                        symlink_name: .shared
                    example/beta:
                        symlink_name: .shared
                """,
    )

    with pytest.raises(PkglinkConfigError) as excinfo:
        load_contexts(config_path=config_path)

    message = str(excinfo.value)
    assert 'symlink_name conflicts' in message
    assert "'.shared'" in message
    assert 'alpha' in message
    assert 'beta' in message
