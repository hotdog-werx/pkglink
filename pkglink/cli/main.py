"""Main CLI entry point for pkglink."""

import argparse
import sys
from pathlib import Path

from pkglink.installation import resolve_source_path
from pkglink.models import LinkOperation, LinkTarget
from pkglink.parsing import parse_source
from pkglink.symlinks import create_symlink


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog='pkglink',
        description='Create symlinks to directories from repositories and Python packages',
    )

    parser.add_argument(
        'source',
        help='Source specification (github:org/repo, package-name, or local path)',
    )
    parser.add_argument(
        'directory',
        nargs='?',
        default='resources',
        help='Directory to link (default: resources)',
    )
    parser.add_argument(
        '--symlink-name',
        help='Custom name for the symlink',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing symlinks',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without doing it',
    )
    return parser


def main() -> None:
    """Main entry point for the pkglink CLI."""
    parser = create_parser()
    args = parser.parse_args()

    try:
        # Parse the source specification
        spec = parse_source(args.source)

        # Resolve the source path
        if args.dry_run:
            print(f'Would resolve source: {args.source}')  # noqa: T201
            return

        source_path = resolve_source_path(spec)

        # Create link target
        target = LinkTarget(
            source_path=source_path,
            target_directory=args.directory,
            symlink_name=args.symlink_name,
        )

        # Create link operation
        operation = LinkOperation(
            spec=spec,
            target=target,
            force=args.force,
            dry_run=args.dry_run,
        )

        # Check if source directory exists
        if not operation.full_source_path.exists():
            print(
                f'Error: Source directory not found: {operation.full_source_path}',
                file=sys.stderr,
            )
            sys.exit(1)

        # Create the symlink
        target_path = Path.cwd() / operation.symlink_name
        is_symlink = create_symlink(
            operation.full_source_path,
            target_path,
            force=args.force,
        )

        if is_symlink:
            print(
                f'Created symlink: {target_path} -> {operation.full_source_path}',
            )
        else:
            print(f'Created copy: {target_path} (symlinks not supported)')  # noqa: T201

    except Exception as e:  # noqa: BLE001
        print(f'Error: {e}', file=sys.stderr)  # noqa: T201
        sys.exit(1)


if __name__ == '__main__':
    main()
