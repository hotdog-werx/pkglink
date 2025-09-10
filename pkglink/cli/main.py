"""Main CLI entry point for pkglink."""

import argparse
import logging
import sys
from pathlib import Path

from pkglink.installation import resolve_source_path
from pkglink.models import LinkOperation, LinkTarget
from pkglink.parsing import parse_source
from pkglink.symlinks import create_symlink

logger = logging.getLogger(__name__)


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
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging',
    )
    parser.add_argument(
        '--from',
        dest='from_package',
        help='Installable package name (when different from module name)',
    )
    return parser


def configure_logging(*, verbose: bool) -> None:
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(levelname)s:%(name)s:%(message)s',
        handlers=[logging.StreamHandler(sys.stderr)],
    )


def main() -> None:
    """Main entry point for the pkglink CLI."""
    parser = create_parser()
    args = parser.parse_args()

    # Configure logging first
    configure_logging(verbose=args.verbose)
    
    logger.info('Starting pkglink with args: %s', vars(args))

    try:
        # Handle --from logic: install one package but look for another module
        if args.from_package:
            logger.info('Using --from: installing %s but looking for module %s', args.from_package, args.source)
            # Parse the package to install
            install_spec = parse_source(args.from_package)
            logger.info('Parsed install spec: %s', install_spec)
            
            # Use the source as the module name to find
            module_name = args.source
            logger.info('Will look for module: %s', module_name)
        else:
            # Normal case: source is both what to install and what to find
            logger.info('Normal mode: parsing source specification: %s', args.source)
            install_spec = parse_source(args.source)
            module_name = install_spec.name
            logger.info('Parsed source spec: %s', install_spec)

        # Handle dry-run early
        if args.dry_run:
            logger.info('Dry run mode - would install: %s', install_spec)
            logger.info('Would look for module: %s', module_name)
            logger.info('Would look for directory: %s', args.directory)
            logger.info('Would create symlink name: %s', args.symlink_name or f'.{module_name}')
            return

        # Resolve the source path using install_spec but look for module_name
        logger.info('Resolving source path for install_spec: %s, module: %s', install_spec, module_name)
        source_path = resolve_source_path(install_spec, module_name)
        logger.info('Resolved source path: %s', source_path)

        # Create link target
        target = LinkTarget(
            source_path=source_path,
            target_directory=args.directory,
            symlink_name=args.symlink_name,
        )
        logger.info('Created link target: %s', target)

        # Create link operation
        operation = LinkOperation(
            spec=install_spec,
            target=target,
            force=args.force,
            dry_run=args.dry_run,
        )
        logger.info('Created link operation: %s', operation)

        # Check if source directory exists
        logger.info('Checking if source directory exists: %s', operation.full_source_path)
        if not operation.full_source_path.exists():
            logger.error('Source directory not found: %s', operation.full_source_path)
            
            # Log contents of parent directory for debugging
            parent_dir = operation.full_source_path.parent
            if parent_dir.exists():
                logger.info('Parent directory contents: %s', list(parent_dir.iterdir()))
            
            sys.stderr.write(f'Error: Source directory not found: {operation.full_source_path}\n')
            sys.exit(1)

        # Create the symlink
        target_path = Path.cwd() / operation.symlink_name
        logger.info('Creating symlink: %s -> %s', target_path, operation.full_source_path)
        
        is_symlink = create_symlink(
            operation.full_source_path,
            target_path,
            force=args.force,
        )

        if is_symlink:
            sys.stdout.write(f'Created symlink: {target_path} -> {operation.full_source_path}\n')
            logger.info('Successfully created symlink')
        else:
            sys.stdout.write(f'Created copy: {target_path} (symlinks not supported)\n')
            logger.info('Successfully created copy (symlinks not supported)')

    except Exception as e:
        logger.exception('CLI operation failed')
        sys.stderr.write(f'Error: {e}\n')
        sys.exit(1)


if __name__ == '__main__':
    main()
