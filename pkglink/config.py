"""Utilities for reading pkglink configuration from YAML."""

from argparse import ArgumentTypeError
from collections.abc import Iterable
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
    """Raised when pkglink configuration is invalid."""


class LinkOptions(BaseModel):
    """Optional values that can be applied to each pkglink link."""

    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    directory: str | None = None
    symlink_name: str | None = None
    inside_pkglink: bool | None = None
    skip_resources: bool | None = None
    no_setup: bool | None = None
    force: bool | None = None
    project_name: str | None = None
    dry_run: bool | None = None
    verbose: int | None = None
    from_spec: str | None = Field(default=None, alias='from')


class LinkDefinition(LinkOptions):
    """Represents a single link definition in pkglink.config.yaml."""

    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    source: str


class PkglinkConfig(BaseModel):
    """Top-level configuration documented in pkglink.config.yaml."""

    model_config = ConfigDict(extra='forbid')

    defaults: LinkOptions = Field(default_factory=LinkOptions)
    links: dict[str, LinkDefinition] = Field(default_factory=dict)


def _load_yaml_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        msg = f'configuration file not found: {config_path}'
        raise PkglinkConfigError(msg)

    logger.debug('loading_config', config=str(config_path))
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


def _parse_directory(raw_directory: str | None, defaults: LinkOptions) -> str:
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
        msg = f'invalid source "{value}" for link {context_label}'
        raise PkglinkConfigError(msg) from exc


def _maybe_parse_source(
    value: str | None,
    *,
    context_label: str,
) -> ParsedSource | None:
    if value is None:
        return None
    return _parse_source(value, context_label=context_label)


def _resolve_bool(*candidates: bool | None, default: bool = False) -> bool:
    for candidate in candidates:
        if candidate is not None:
            return candidate
    return default


def _collect_duplicates(
    pairs: Iterable[tuple[str, str | None]],
) -> dict[str, list[str]]:
    registry: dict[str, list[str]] = {}
    for entry_name, value in pairs:
        if not value:
            continue
        if value not in registry:
            registry[value] = [entry_name]
        else:
            registry[value].append(entry_name)
    return {value: entries for value, entries in registry.items() if len(entries) > 1}


def _entry_label(context: PkglinkContext) -> str:
    return getattr(context.cli_args, 'entry_name', context.get_display_name())


def _group_contexts_by_project(
    ctxs: list[PkglinkContext],
) -> dict[str, list[PkglinkContext]]:
    """Group contexts by their install_spec.project_name."""
    groups: dict[str, list[PkglinkContext]] = {}
    for c in ctxs:
        groups.setdefault(c.install_spec.project_name, []).append(c)
    return groups


def _find_project_duplicates(
    groups: dict[str, list[PkglinkContext]],
) -> dict[str, list[str]]:
    """Return mapping of project_name -> list of conflicting entry labels.

    A project is considered conflicting unless all entries share the same
    install spec and at most one installs inside the pkglink cache.
    """
    duplicates: dict[str, list[str]] = {}
    for project_name, group in groups.items():
        if len(group) <= 1:
            continue

        baseline_spec = group[0].install_spec.model_dump()
        same_install_spec = all(baseline_spec == other.install_spec.model_dump() for other in group[1:])
        inside_count = sum(1 for ctx in group if ctx.inside_pkglink)

        # Allow duplicates when all entries refer to the exact same install spec
        # and at most one of them installs inside the pkglink cache.
        if same_install_spec and inside_count <= 1:
            continue

        duplicates[project_name] = [_entry_label(ctx) for ctx in group]

    return duplicates


def _format_conflict_message(
    project_conflicts: dict[str, list[str]],
    symlink_conflicts: dict[str, list[str]],
) -> str:
    """Format a user-friendly error message for detected conflicts."""
    lines: list[str] = ['duplicate link targets detected:']

    if project_conflicts:
        lines.append('project_name conflicts:')
        for project_name, entries in project_conflicts.items():
            entry_list = ', '.join(entries)
            lines.append(f"  '{project_name}' used by: {entry_list}")

    if symlink_conflicts:
        lines.append('symlink_name conflicts:')
        for symlink_name, entries in symlink_conflicts.items():
            entry_list = ', '.join(entries)
            lines.append(f"  '{symlink_name}' used by: {entry_list}")

    lines.append(
        'Each project_name and symlink_name must be unique across links.',
    )
    return '\n'.join(lines)


def _ensure_unique_link_targets(contexts: list[PkglinkContext]) -> None:
    project_groups = _group_contexts_by_project(contexts)
    project_duplicates = _find_project_duplicates(project_groups)

    symlink_duplicates = _collect_duplicates(
        (_entry_label(context), context.resolved_symlink_name) for context in contexts
    )

    if not project_duplicates and not symlink_duplicates:
        return

    raise PkglinkConfigError(
        _format_conflict_message(project_duplicates, symlink_duplicates),
    )


def load_config(config_path: Path) -> PkglinkConfig:
    """Load pkglink configuration from YAML."""
    config_data = _load_yaml_config(config_path)

    try:
        config = PkglinkConfig.model_validate(config_data)
    except ValidationError as exc:
        logger.exception('config_validation_failed', errors=exc.errors())
        msg = 'invalid pkglink configuration'
        raise PkglinkConfigError(msg) from exc

    if not config.links:
        msg = f'no links defined in {config_path}'
        raise PkglinkConfigError(msg)

    return config


def build_contexts(
    config: PkglinkConfig,
    *,
    config_path: Path,
    global_verbose: int = 0,
    global_dry_run: bool = False,
) -> list[PkglinkContext]:
    """Create pkglink contexts from a loaded configuration."""
    contexts: list[PkglinkContext] = []

    for entry_name, entry in config.links.items():
        logger.debug('resolving_link_entry', entry=entry_name)

        parsed_source = _parse_source(entry.source, context_label=entry_name)

        defaults = config.defaults
        from_candidate = entry.from_spec or defaults.from_spec
        from_source = _maybe_parse_source(
            from_candidate,
            context_label=entry_name,
        )
        directory = _parse_directory(entry.directory, defaults)

        symlink_name = entry.symlink_name or defaults.symlink_name
        project_name = entry.project_name or defaults.project_name
        no_setup = _resolve_bool(entry.no_setup, defaults.no_setup)
        force = _resolve_bool(entry.force, defaults.force)
        skip_resources = _resolve_bool(
            entry.skip_resources,
            defaults.skip_resources,
        )
        inside_pkglink = _resolve_bool(
            entry.inside_pkglink,
            defaults.inside_pkglink,
            default=True,  # Default to pkglinkx behavior (install in .pkglink/)
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
            entry_name=entry_name,
            cli_label='pkglink_batch',
            config_path=str(config_path),
        )

        context = create_pkglink_context(cli_args)
        contexts.append(context)

    _ensure_unique_link_targets(contexts)

    return contexts


def load_contexts(
    config_path: Path,
    *,
    global_verbose: int = 0,
    global_dry_run: bool = False,
) -> list[PkglinkContext]:
    """Convenience wrapper to load configuration and build contexts."""
    config = load_config(config_path)
    return build_contexts(
        config,
        config_path=config_path,
        global_verbose=global_verbose,
        global_dry_run=global_dry_run,
    )


__all__ = [
    'DEFAULT_CONFIG_FILENAME',
    'LinkDefinition',
    'LinkOptions',
    'PkglinkConfig',
    'PkglinkConfigError',
    'build_contexts',
    'load_config',
    'load_contexts',
]
