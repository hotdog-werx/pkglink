"""Unified pkglink CLI wrapping link, tool, and sync workflows."""

import argparse
import sys

from pkglink.cli.subparsers import register_all
from pkglink.version import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        description='Unified pkglink CLI',
    )
    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s ' + __version__,
    )
    subparsers = parser.add_subparsers(dest='command', required=True)
    register_all(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the pkglink CLI."""
    parser = build_parser()
    namespace = parser.parse_args(argv)

    handler = getattr(namespace, 'handler', None)
    if handler is None:
        parser.print_help()
        return 1

    return handler(namespace)


if __name__ == '__main__':
    sys.exit(main())
