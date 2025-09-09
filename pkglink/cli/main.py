"""Main CLI entry point for pkglink."""

import argparse
import sys
from pathlib import Path

from pkglink.installation import resolve_source_path
from pkglink.models import LinkOperation, LinkTarget
from pkglink.parsing import parse_source
from pkglink.symlinks import create_symlink, list_managed_links, remove_target


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog='pkglink',
        description='Create symlinks to directories from repositories and Python packages',
    )

    subparsers = parser.add_subparsers(
        dest='command',
        help='Available commands',
    )

    # Link command (default)
    link_parser = subparsers.add_parser('link', help='Create a symlink')
    link_parser.add_argument(
        'source',
        help='Source specification (github:org/repo, package-name, or local path)',
    )
    link_parser.add_argument(
        'directory',
        nargs='?',
        default='resources',
        help='Directory to link (default: resources)',
    )
    link_parser.add_argument(
        '--symlink-name',
        help='Custom name for the symlink',
    )
    link_parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing symlinks',
    )
    link_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without doing it',
    )

    # List command
    list_parser = subparsers.add_parser('list', help='List managed symlinks')
    list_parser.add_argument(
        '--directory',
        type=Path,
        help='Directory to list (default: current)',
    )

    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove a symlink')
    remove_parser.add_argument('name', help='Name of the symlink to remove')

    return parser


def handle_link_command(args: argparse.Namespace) -> int:
    """Handle the link command."""
    try:
        # Parse the source specification
        spec = parse_source(args.source)

        # Resolve the source path
        if args.dry_run:
            print(f'Would resolve source: {args.source}')  # noqa: T201
            return 0

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
            return 1

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

        return 0

    except Exception as e:  # noqa: BLE001
        print(f'Error: {e}', file=sys.stderr)  # noqa: T201
        return 1


def handle_list_command(args: argparse.Namespace) -> int:
    """Handle the list command."""
    directory = args.directory or Path.cwd()
    links = list_managed_links(directory)

    if not links:
        print('No managed symlinks found')  # noqa: T201
        return 0

    for link in links:
        if link.is_symlink():
            target = link.readlink()
            print(f'{link.name} -> {target}')  # noqa: T201
        else:
            print(f'{link.name} (copy)')  # noqa: T201

    return 0


def handle_remove_command(args: argparse.Namespace) -> int:
    """Handle the remove command."""
    target_path = Path.cwd() / args.name

    if not target_path.exists():
        print(f'Error: {args.name} does not exist', file=sys.stderr)  # noqa: T201
        return 1

    try:
        remove_target(target_path)
        print(f'Removed: {args.name}')  # noqa: T201
        return 0
    except Exception as e:  # noqa: BLE001
        print(f'Error removing {args.name}: {e}', file=sys.stderr)  # noqa: T201
        return 1


def main() -> None:
    """Main entry point for the pkglink CLI."""
    parser = create_parser()

    # Handle case where no subcommand is provided - default to link
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    # If first arg doesn't match a subcommand, treat it as link command
    if sys.argv[1] not in ['list', 'remove']:
        # Insert 'link' as the command
        sys.argv.insert(1, 'link')

    args = parser.parse_args()

    if args.command == 'link':
        exit_code = handle_link_command(args)
    elif args.command == 'list':
        exit_code = handle_list_command(args)
    elif args.command == 'remove':
        exit_code = handle_remove_command(args)
    else:
        parser.print_help()
        exit_code = 1

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
