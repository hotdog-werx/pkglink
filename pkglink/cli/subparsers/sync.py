"""pkglink sync subcommand."""

import argparse
from pathlib import Path

from hotlog import get_logger

from pkglink.cli.common import (
    WorkflowEntry,
    download_phase,
    execution_phase,
    handle_cli_exception,
    planning_phase,
    setup_logging_and_handle_errors,
)
from pkglink.config import (
    DEFAULT_CONFIG_FILENAME,
    load_contexts,
)
from pkglink.uvx import refresh_package

from . import _shared

logger = get_logger(__name__)


def _refresh_package_for_entry(entry: WorkflowEntry) -> None:
    """Refresh package in uvx for entries installed in .pkglink/.

    Extracted to reduce cyclomatic complexity of run_batch.
    """
    context = entry.context
    if not context.inside_pkglink:
        return

    target_dir = Path('.pkglink') / context.install_spec.project_name
    if not target_dir.exists():
        return

    success = refresh_package(
        context.module_name,
        target_dir,
    )
    if success:
        logger.info(
            'uvx_refresh_successful',
            package=context.module_name,
            _display_level=1,
        )
    else:
        logger.warning(
            'uvx_refresh_failed',
            package=context.module_name,
        )


def run_batch(
    *,
    config_path: Path,
    verbose: int = 0,
    dry_run: bool = False,
    entry_filters: tuple[str, ...] | None = None,
) -> int:
    """Execute the batch workflow for the provided configuration."""
    setup_logging_and_handle_errors(verbose=verbose)

    try:
        contexts = load_contexts(
            config_path,
            global_verbose=verbose,
            global_dry_run=dry_run,
        )

        if entry_filters:
            filters = {entry.strip() for entry in entry_filters}
            contexts = [context for context in contexts if getattr(context.cli_args, 'entry_name', '') in filters]

        entries = [WorkflowEntry(context=context) for context in contexts]

        download_phase(entries)
        planning_phase(entries)
        execution_phase(entries, post_execution=_refresh_package_for_entry)
    except Exception as exc:  # noqa: BLE001 - top-level CLI guard
        handle_cli_exception(exc)
    else:
        return 0
    return 1


def _handle(namespace: argparse.Namespace) -> int:
    verbose = _shared.resolve_verbose(namespace)
    entry_filters = _shared.parse_known_entries(namespace.entries)
    config_path = Path(namespace.config).resolve()
    return run_batch(
        config_path=config_path,
        verbose=verbose,
        dry_run=namespace.dry_run,
        entry_filters=entry_filters,
    )


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the sync subcommand."""
    parent = _shared.build_common_parent()
    parser = subparsers.add_parser(
        'sync',
        parents=[parent],
        aliases=['batch'],
        help='Synchronize links defined in pkglink.config.yaml',
    )
    parser.add_argument(
        '--config',
        default=DEFAULT_CONFIG_FILENAME,
        help='Path to pkglink configuration file (default: %(default)s)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Generate plans without executing operations',
    )
    _shared.filter_entries_argument(parser)
    parser.set_defaults(handler=_handle)
