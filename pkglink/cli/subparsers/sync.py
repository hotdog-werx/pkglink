"""plk sync subcommand."""

import argparse
from pathlib import Path

from pkglink.cli.pkglink_batch import run_batch
from pkglink.config import DEFAULT_CONFIG_FILENAME

from . import _shared


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
