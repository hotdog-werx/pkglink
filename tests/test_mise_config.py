from pathlib import Path

import pytest

from pkglink.batch_config import (
    DEFAULT_CONFIG_FILENAME,
    PkglinkConfigError,
    load_batch_contexts,
)


def write_config(tmp_path: Path, content: str) -> Path:
    config_path = tmp_path / DEFAULT_CONFIG_FILENAME
    config_path.write_text(content)
    return config_path


def test_global_overrides_apply(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
        defaults:
          inside_pkglink: false

        targets:
          - name: verbose_override
            source: github:hotdog-werx/pkglink-integration-pkg@v0.0.1
            verbose: 3
            dry_run: false

          - name: inherit_global
            source: github:hotdog-werx/pkglink-integration-pkg@v0.0.1
        """,
    )

    contexts = load_batch_contexts(
        config_path,
        global_verbose=1,
        global_dry_run=True,
    )

    assert len(contexts) == 2

    first, second = contexts
    assert first.cli_args.verbose == 3
    assert first.cli_args.dry_run is False

    assert second.cli_args.verbose == 1
    assert second.cli_args.dry_run is True


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    config_path = write_config(tmp_path, "targets: [invalid")

    with pytest.raises(PkglinkConfigError):
        load_batch_contexts(config_path)


def test_non_mapping_root_raises(tmp_path: Path) -> None:
    config_path = write_config(tmp_path, "- not-a-mapping")

    with pytest.raises(PkglinkConfigError):
        load_batch_contexts(config_path)
