"""Post-install setup functionality for pkglink."""

from pathlib import Path
from typing import Any

import yaml
from hotlog import get_logger
from pydantic import BaseModel

from pkglink.symlinks import create_symlink

logger = get_logger(__name__)


class SymlinkSpec(BaseModel):
    """Specification for a single symlink."""

    source: str
    target: str


class PostInstallConfig(BaseModel):
    """Configuration for post-install setup."""

    symlinks: list[SymlinkSpec] = []


def _load_yaml_config(config_path: Path) -> dict[str, Any]:
    """Load and parse YAML configuration file."""
    with config_path.open() as f:
        return yaml.safe_load(f) or {}


def _find_config_file(linked_path: Path) -> Path | None:
    """Find pkglink.yaml configuration file in linked directory."""
    config_path = linked_path / 'pkglink.yaml'
    return config_path if config_path.exists() else None


def _create_additional_symlink(
    spec: SymlinkSpec,
    linked_path: Path,
    base_dir: Path,
) -> None:
    """Create a single additional symlink from the configuration."""
    source = linked_path / spec.source
    target = base_dir / spec.target
    create_symlink(
        source,
        target,
        force=True,
        allow_additional_symlink_removal=True,
    )


def _process_symlinks(
    config: PostInstallConfig,
    linked_path: Path,
    base_dir: Path,
) -> None:
    """Process all symlinks from the configuration."""
    for spec in config.symlinks:
        _create_additional_symlink(spec, linked_path, base_dir)


def run_post_install_setup(
    linked_path: Path,
    base_dir: Path,
) -> None:
    """Run post-install setup for a linked package."""
    config_path = _find_config_file(linked_path)
    if not config_path:
        logger.debug(
            'no_post_install_config_found',
            linked_path=str(linked_path),
        )
        return

    logger.info('running_post_install_setup', config_path=str(config_path))

    try:
        yaml_data = _load_yaml_config(config_path)
        config = PostInstallConfig.model_validate(yaml_data)
        _process_symlinks(config, linked_path, base_dir)
        logger.info(
            'post_install_setup_completed',
            symlinks_created=len(config.symlinks),
        )
    except Exception as e:  # noqa: BLE001 - broad exception to catch all setup errors
        # A bad setup configuration should not block the main install
        # But we may need to add a flag later to make this stricter
        logger.warning('post_install_setup_failed', error=str(e))
