"""Utilities for reading pkglink configuration from YAML."""

from argparse import ArgumentTypeError
from collections.abc import Iterable
from dataclasses import dataclass
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


@dataclass
class NormalizedEntry:
    """Internal representation of a config entry after normalization."""

    source: str
    directory: str | None = None
    symlink_name: str | None = None
    inside_pkglink: bool | None = None
    skip_resources: bool | None = None
    no_setup: bool | None = None
    force: bool | None = None
    project_name: str | None = None
    dry_run: bool | None = None
    verbose: int | None = None
    from_spec: str | None = None


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


class GitHubEntry(LinkOptions):
    """GitHub repository entry with optional version."""

    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    version: str | None = None


class PythonPackageEntry(LinkOptions):
    """Python package entry from PyPI."""

    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    version: str | None = None


class LocalEntry(LinkOptions):
    """Local path entry."""

    model_config = ConfigDict(extra='forbid', populate_by_name=True)


class PkglinkConfig(BaseModel):
    """Top-level configuration documented in pkglink.config.yaml."""

    model_config = ConfigDict(extra='forbid')

    defaults: LinkOptions = Field(default_factory=LinkOptions)
    github: dict[str, str | GitHubEntry] | None = None
    python_packages: dict[str, str | PythonPackageEntry] | None = Field(
        default=None,
        alias='python-packages',
    )
    local: dict[str, str | LocalEntry] | None = None


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


def _normalize_github_entry(
    key: str,
    value: str | GitHubEntry,
) -> NormalizedEntry:
    """Convert GitHub entry to NormalizedEntry."""
    # key format: "org/repo"
    if '/' not in key or key.count('/') != 1:
        msg = f"github entry key '{key}' must be in 'org/repo' format"
        raise PkglinkConfigError(msg)
    if isinstance(value, str):
        # Simple format: "org/repo: version"
        source = f'github:{key}@{value}'
        return NormalizedEntry(source=source)

    # Detailed format
    # If all fields are None, treat as invalid
    if all(
        getattr(value, field) is None
        for field in [
            'version',
            'directory',
            'symlink_name',
            'inside_pkglink',
            'skip_resources',
            'no_setup',
            'force',
            'project_name',
            'dry_run',
            'verbose',
            'from_spec',
        ]
    ):
        msg = f"github entry '{key}' is missing required fields"
        raise PkglinkConfigError(msg)

    version = value.version or 'master'
    source = f'github:{key}@{version}'
    kwargs = {
        'source': source,
        'directory': value.directory,
        'symlink_name': value.symlink_name,
        'inside_pkglink': value.inside_pkglink,
        'skip_resources': value.skip_resources,
        'no_setup': value.no_setup,
        'force': value.force,
        'project_name': value.project_name,
        'dry_run': value.dry_run,
        'verbose': value.verbose,
    }
    if value.from_spec is not None:
        kwargs['from_spec'] = value.from_spec
    return NormalizedEntry(**kwargs)


def _normalize_python_package_entry(
    key: str,
    value: str | PythonPackageEntry,
) -> NormalizedEntry:
    """Convert Python package entry to NormalizedEntry."""
    # key is the package name
    if isinstance(value, str):
        # Simple format with version specifier: "package: >=1.0.0"
        # or just package name (latest)
        source = f'{key}{value}' if value else key
        return NormalizedEntry(source=source)

    # Detailed format
    source = key
    if value.version:
        source = f'{key}{value.version}'
    kwargs = {
        'source': source,
        'directory': value.directory,
        'symlink_name': value.symlink_name,
        'inside_pkglink': value.inside_pkglink,
        'skip_resources': value.skip_resources,
        'no_setup': value.no_setup,
        'force': value.force,
        'project_name': value.project_name,
        'dry_run': value.dry_run,
        'verbose': value.verbose,
    }
    if value.from_spec is not None:
        kwargs['from_spec'] = value.from_spec
    return NormalizedEntry(**kwargs)


def _normalize_local_entry(
    key: str,
    value: str | LocalEntry,
) -> NormalizedEntry:
    """Convert local path entry to NormalizedEntry."""
    # key is the path
    if isinstance(value, str):
        # Simple format - value is empty string, key is the path
        source = f'local:{key}'
        return NormalizedEntry(source=source)

    # Detailed format
    source = f'local:{key}'
    kwargs = {
        'source': source,
        'directory': value.directory,
        'symlink_name': value.symlink_name,
        'inside_pkglink': value.inside_pkglink,
        'skip_resources': value.skip_resources,
        'no_setup': value.no_setup,
        'force': value.force,
        'project_name': value.project_name,
        'dry_run': value.dry_run,
        'verbose': value.verbose,
    }
    if value.from_spec is not None:
        kwargs['from_spec'] = value.from_spec
    return NormalizedEntry(**kwargs)


def _process_github_entries(
    github: dict[str, str | GitHubEntry],
    links: dict[str, NormalizedEntry],
) -> None:
    if not github:
        return
    for key, value in github.items():
        entry_name = key.split('/')[-1]
        if entry_name in links:
            entry_name = key.replace('/', '_')
        links[entry_name] = _normalize_github_entry(key, value)


def _process_python_package_entries(
    packages: dict[str, str | PythonPackageEntry],
    links: dict[str, NormalizedEntry],
) -> None:
    if not packages:
        return
    for key, value in packages.items():
        entry_name = key
        if entry_name in links:
            entry_name = f'pkg_{key}'
        links[entry_name] = _normalize_python_package_entry(key, value)


def _process_local_entries(
    local: dict[str, str | LocalEntry],
    links: dict[str, NormalizedEntry],
) -> None:
    if not local:
        return
    for key, value in local.items():
        entry_name = Path(key).name
        if entry_name in links:
            entry_name = f'local_{Path(key).name}'
        links[entry_name] = _normalize_local_entry(key, value)


def _convert_to_links(config: PkglinkConfig) -> dict[str, NormalizedEntry]:
    """Convert new structured format to unified links format."""
    links: dict[str, NormalizedEntry] = {}
    _process_github_entries(config.github or {}, links)
    _process_python_package_entries(config.python_packages or {}, links)
    _process_local_entries(config.local or {}, links)
    return links


def load_config(
    config_path: Path,
) -> tuple[PkglinkConfig, dict[str, NormalizedEntry]]:
    """Load pkglink configuration from YAML.

    Returns:
        Tuple of (config, normalized_links) where normalized_links is a dict
        of entry_name -> NormalizedEntry ready for context building.
    """
    config_data = _load_yaml_config(config_path)

    try:
        config = PkglinkConfig.model_validate(config_data)
    except ValidationError as exc:
        logger.exception('config_validation_failed', errors=exc.errors())
        msg = 'invalid pkglink configuration'
        raise PkglinkConfigError(msg) from exc

    # Convert structured format to normalized entries
    has_any_links = config.github or config.python_packages or config.local
    if not has_any_links:
        msg = f'no links defined in {config_path}'
        raise PkglinkConfigError(msg)

    normalized_links = _convert_to_links(config)
    return config, normalized_links


def build_contexts(
    config: PkglinkConfig,
    normalized_links: dict[str, NormalizedEntry],
    *,
    config_path: Path,
    global_verbose: int = 0,
    global_dry_run: bool = False,
) -> list[PkglinkContext]:
    """Create pkglink contexts from a loaded configuration."""
    contexts: list[PkglinkContext] = []

    for entry_name, entry in normalized_links.items():
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
    config, normalized_links = load_config(config_path)
    return build_contexts(
        config,
        normalized_links,
        config_path=config_path,
        global_verbose=global_verbose,
        global_dry_run=global_dry_run,
    )


__all__ = [
    'DEFAULT_CONFIG_FILENAME',
    'LinkOptions',
    'NormalizedEntry',
    'PkglinkConfig',
    'PkglinkConfigError',
    'build_contexts',
    'load_config',
    'load_contexts',
]
