"""Main entry point for the pkglink CLI."""

import sys
from pathlib import Path

from pkglink.installation import resolve_source_path
from pkglink.logging import configure_logging, get_logger
from pkglink.models import CliArgs, LinkOperation, LinkTarget, SourceSpec
from pkglink.parsing import (
    determine_install_spec_and_module,
    parse_args_to_model,
)
from pkglink.symlinks import create_symlink

logger = get_logger(__name__)


def handle_dry_run(
    args: CliArgs,
    install_spec: SourceSpec,
    module_name: str,
) -> None:
    """Handle dry run mode by logging what would be done."""
    if not args.dry_run:
        return

    logger.info(
        'dry_run_mode',
        directory=args.directory,
        module_name=module_name,
        symlink_name=args.symlink_name or f'.{module_name}',
        _verbose_install_spec=install_spec.model_dump(),
    )


def execute_symlink_operation(args: CliArgs, operation: LinkOperation) -> None:
    """Execute the actual symlink creation operation."""
    # Check if source directory exists
    logger.info(
        'checking_source_directory',
        path=str(operation.full_source_path),
    )

    if not operation.full_source_path.exists():
        logger.error(
            'source_directory_not_found',
            path=str(operation.full_source_path),
        )

        # Log contents of parent directory for debugging
        parent_dir = operation.full_source_path.parent
        if parent_dir.exists():
            logger.info(
                'parent_directory_contents',
                parent=str(parent_dir),
                contents=[str(p) for p in parent_dir.iterdir()],
            )

        sys.stderr.write(
            f'Error: Source directory not found: {operation.full_source_path}\n',
        )
        sys.exit(1)

    # Create the symlink
    target_path = Path.cwd() / operation.symlink_name
    logger.info(
        'creating_symlink',
        target=str(target_path),
        source=str(operation.full_source_path),
    )

    is_symlink = create_symlink(
        operation.full_source_path,
        target_path,
        force=args.force,
    )

    if is_symlink:
        logger.info(
            'symlink_created_successfully',
            target=str(target_path),
            source=str(operation.full_source_path),
        )
    else:
        logger.info(
            'copy_created_successfully',
            target=str(target_path),
            reason='symlinks not supported',
        )


def main() -> None:
    """Main entry point for the pkglink CLI."""
    args = parse_args_to_model()

    # Configure logging first
    configure_logging(verbose=args.verbose)

    logger.info(
        'starting_pkglink',
        source=args.source,
        directory=args.directory,
        dry_run=args.dry_run,
        force=args.force,
        _verbose_args=args.model_dump(),
    )

    try:
        install_spec, module_name = determine_install_spec_and_module(args)

        # Check if target already exists first (before any installation work)
        symlink_name = args.symlink_name or f'.{install_spec.name}'
        target_path = Path.cwd() / symlink_name
        
        if target_path.exists() and not args.force:
            logger.info(
                'target_already_exists_skipping',
                target=str(target_path),
                symlink_name=symlink_name,
            )
            return

        # Handle dry-run early
        handle_dry_run(args, install_spec, module_name)
        if args.dry_run:
            return

        # Resolve the source path using install_spec but look for module_name
        logger.info(
            'resolving_source_path',
            module=module_name,
            _verbose_install_spec=install_spec.model_dump(),
        )

        source_path = resolve_source_path(install_spec, module_name)
        logger.info('resolved_source_path', path=str(source_path))

        # Create link target
        target = LinkTarget(
            source_path=source_path,
            target_directory=args.directory,
            symlink_name=args.symlink_name,
        )
        logger.info(
            'created_link_target',
            source_path=str(target.source_path),
            target_directory=target.target_directory,
            symlink_name=target.symlink_name,
            _verbose_target=target.model_dump(),
        )

        # Create link operation
        operation = LinkOperation(
            spec=install_spec,
            target=target,
            force=args.force,
            dry_run=args.dry_run,
        )
        logger.info(
            'created_link_operation',
            symlink_name=operation.symlink_name,
            full_source_path=str(operation.full_source_path),
            _verbose_operation=operation.model_dump(),
        )

        execute_symlink_operation(args, operation)

    except Exception as e:
        # Log with safe error representation for YAML serialization
        logger.exception('cli_operation_failed', error=str(e))
        sys.stderr.write(f'Error: {e}\n')
        sys.exit(1)


if __name__ == '__main__':
    main()
