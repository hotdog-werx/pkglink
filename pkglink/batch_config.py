"""Utilities for reading pkglink batch configuration from YAML."""

from __future__ import annotations

from argparse import ArgumentTypeError
from pathlib import Path
from typing import Any

import yaml
from hotlog import get_logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pkglink.argparse import argparse_directory, argparse_source
from pkglink.models import ParsedSource, PkglinkBatchCliArgs, PkglinkContext
from pkglink.parsing import create_pkglink_context

logger = get_logger(__name__)

DEFAULT_CONFIG_FILENAME = 'pkglink.config.yaml'


class PkglinkConfigError(RuntimeError):
    """Raised when batch configuration is invalid."""


class BatchDefaults(BaseModel):
    """Default values applied to each pkglink entry."""

    model_config = ConfigDict(extra='ignore')

    directory: str | None = None
    symlink_name: str | None = None
    inside_pkglink: bool | None = None
    use_pkglink_dir: bool | None = Field(default=None, alias='use_pkglink_dir')
    skip_resources: bool | None = None
    no_setup: bool | None = None
    force: bool | None = None
    project_name: str | None = None
    dry_run: bool | None = None
    verbose: int | None = None


class BatchEntry(BaseModel):
    """Single pkglink entry configuration."""

    model_config = ConfigDict(extra='ignore')

    name: str | None = None
    label: str | None = None
    source: str
    from_spec: str | None = Field(default=None, alias='from')
    directory: str | None = None
    symlink_name: str | None = None
    inside_pkglink: bool | None = None
    use_pkglink_dir: bool | None = Field(default=None, alias='use_pkglink_dir')
    skip_resources: bool | None = None
    no_setup: bool | None = None
    force: bool | None = None
    project_name: str | None = None
    dry_run: bool | None = None
    verbose: int | None = None


class BatchConfig(BaseModel):
    """Top-level batch configuration schema."""

    model_config = ConfigDict(extra='forbid')

    defaults: BatchDefaults = Field(default_factory=BatchDefaults)
    targets: list[BatchEntry] = Field(default_factory=list)


def _load_yaml_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        msg = f'configuration file not found: {config_path}'
        raise PkglinkConfigError(msg)

    logger.debug('loading_batch_config', config=str(config_path))
    try:
        with config_path.open() as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        msg = f'failed to parse YAML: {exc}'
        raise PkglinkConfigError(msg) from exc

    if not isinstance(data, dict):
        msg = f'configuration root must be a mapping in {config_path}'
        raise PkglinkConfigError(msg)

    return data


def _parse_directory(raw_directory: str | None, defaults: BatchDefaults) -> str:
    directory = raw_directory or defaults.directory or 'resources'
    try:
        return argparse_directory(directory)
    except ArgumentTypeError as exc:
        msg = f'invalid directory value "{directory}"'
        raise PkglinkConfigError(msg) from exc


def _parse_source(value: str, *, context_label: str) -> ParsedSource:
    try:
        return argparse_source(value)
    except ArgumentTypeError as exc:
        msg = f'invalid source "{value}" for entry {context_label}'
        raise PkglinkConfigError(msg) from exc


def _maybe_parse_source(value: str | None, *, context_label: str) -> ParsedSource | None:
    if value is None:
        return None
    return _parse_source(value, context_label=context_label)


def _resolve_bool(*candidates: bool | None, default: bool = False) -> bool:
    for candidate in candidates:
        if candidate is not None:
            return candidate
    return default


def _entry_name(entry: BatchEntry, index: int) -> str:
    return entry.name or entry.label or entry.source or f'entry_{index + 1}'


def load_batch_contexts(
    config_path: Path,
    *,
    global_verbose: int = 0,
    global_dry_run: bool = False,
) -> list[PkglinkContext]:
    """Load pkglink contexts from a YAML configuration file."""

    config_data = _load_yaml_config(config_path)

    try:
        config = BatchConfig.model_validate(config_data)
    except ValidationError as exc:
        logger.error('batch_config_validation_failed', errors=exc.errors())
        raise PkglinkConfigError('invalid pkglink batch configuration') from exc

    if not config.targets:
        msg = f'no targets defined in {config_path}'
        raise PkglinkConfigError(msg)

    defaults = config.defaults
    contexts: list[PkglinkContext] = []

    for index, entry in enumerate(config.targets):
        label = _entry_name(entry, index)
        logger.debug('resolving_batch_entry', entry=label)

        parsed_source = _parse_source(entry.source, context_label=label)
        from_source = _maybe_parse_source(entry.from_spec, context_label=label)
        directory = _parse_directory(entry.directory, defaults)

        symlink_name = entry.symlink_name or defaults.symlink_name
        project_name = entry.project_name or defaults.project_name
        no_setup = _resolve_bool(entry.no_setup, defaults.no_setup)
        force = _resolve_bool(entry.force, defaults.force)
        skip_resources = _resolve_bool(entry.skip_resources, defaults.skip_resources)
        inside_pkglink = _resolve_bool(
            entry.inside_pkglink,
            entry.use_pkglink_dir,
            defaults.inside_pkglink,
            defaults.use_pkglink_dir,
        )
        dry_run = _resolve_bool(entry.dry_run, defaults.dry_run, global_dry_run)
        verbose = (
            entry.verbose
            if entry.verbose is not None
            else (defaults.verbose if defaults.verbose is not None else global_verbose)
        )

        cli_args = PkglinkBatchCliArgs(
            source=parsed_source,
            directory=directory,
            symlink_name=symlink_name,
            verbose=verbose,
            from_package=from_source,
            project_name=project_name,
            no_setup=no_setup,
            force=force,
            dry_run=dry_run,
            skip_resources=skip_resources,
            inside_pkglink=inside_pkglink,
            entry_name=label,
            cli_label='pkglink_batch',
            config_path=str(config_path),
        )

        context = create_pkglink_context(cli_args)
        contexts.append(context)

    return contexts


__all__ = [
    'DEFAULT_CONFIG_FILENAME',
    'PkglinkConfigError',
    'load_batch_contexts',
]
