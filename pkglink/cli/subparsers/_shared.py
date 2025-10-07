"""Shared helpers for pkglink subparsers."""

import argparse
from collections.abc import Iterable

from hotlog import add_verbosity_argument, resolve_verbosity

from pkglink.argparse import argparse_directory, argparse_source


def build_common_parent() -> argparse.ArgumentParser:
    """Create a parent parser containing global verbosity options."""
    parent = argparse.ArgumentParser(add_help=False)
    add_verbosity_argument(parent)
    return parent


def apply_install_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_directory: bool = True,
    include_inside: bool = False,
    include_skip_resources: bool = False,
) -> None:
    """Attach shared install-related arguments to the parser."""
    parser.add_argument(
        'source',
        type=argparse_source,
        help='Source specification (github:org/repo, package-name, or local path)',
    )

    if include_directory:
        parser.add_argument(
            'directory',
            nargs='?',
            default='resources',
            type=argparse_directory,
            help='Directory to link (default: resources)',
        )

    parser.add_argument(
        '--symlink-name',
        help='Custom name for the symlink',
    )

    parser.add_argument(
        '--from',
        dest='from_package',
        type=argparse_source,
        help='Installable package name when different from module name',
    )
    parser.add_argument(
        '--project-name',
        dest='project_name',
        help='PyPI project name (for GitHub repos with different package names)',
    )
    parser.add_argument(
        '--no-setup',
        action='store_true',
        help='Skip running post-install setup',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing symlinks',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without executing',
    )

    if include_inside:
        parser.add_argument(
            '--inside',
            action='store_true',
            help='Create the symlink inside the .pkglink directory',
        )

    if include_skip_resources:
        parser.add_argument(
            '--skip-resources',
            action='store_true',
            help='Skip creating resource symlinks',
        )


def resolve_verbose(namespace: argparse.Namespace) -> int:
    """Resolve verbosity level from parsed namespace."""
    return resolve_verbosity(namespace)


def filter_entries_argument(parser: argparse.ArgumentParser) -> None:
    """Add the --entry option supporting multiple filters."""
    parser.add_argument(
        '--entry',
        dest='entries',
        action='append',
        help='Limit sync to specific configuration entry names',
    )


def parse_known_entries(
    entries: Iterable[str] | None,
) -> tuple[str, ...] | None:
    """Normalize an iterable of entry names into a tuple."""
    if not entries:
        return None
    return tuple(entries)
