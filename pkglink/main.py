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


def setup_logging(args: CliArgs | None = None) -> None:
    """Configure logging with appropriate verbosity."""
    verbose = args.verbose if args else False
    configure_logging(verbose=verbose)


def log_startup_info(args: CliArgs) -> None:
    """Log startup information for the pkglink operation."""
    logger.info(
        'starting_pkglink',
        source=args.source,
        directory=args.directory,
        dry_run=args.dry_run,
        force=args.force,
        _verbose_args=args.model_dump(),
    )


def _is_symlink_pointing_to_correct_target(
    target_path: Path,
    expected_target: Path,
) -> bool:
    """Check if symlink points to the expected target."""
    try:
        if not target_path.is_symlink():
            logger.debug(
                'target_exists_but_not_symlink',
                target=str(target_path),
            )
            return False

        current_target = target_path.resolve()
        if current_target == expected_target:
            return True

        logger.debug(
            'target_exists_but_points_to_wrong_location',
            target=str(target_path),
            current_target=str(current_target),
            expected_target=str(expected_target),
        )
    except (OSError, RuntimeError):
        logger.debug(
            'target_exists_but_cannot_resolve',
            target=str(target_path),
        )

    return False


def check_target_exists(
    args: CliArgs,
    install_spec: SourceSpec,
    expected_source_path: Path,
) -> bool:
    """Check if target symlink already exists and points to the correct source."""
    symlink_name = args.symlink_name or f'.{install_spec.name}'
    target_path = Path.cwd() / symlink_name

    if not target_path.exists():
        return False

    if args.force:
        logger.debug('force_flag_set_will_overwrite', target=str(target_path))
        return False

    expected_target = expected_source_path / args.directory
    if _is_symlink_pointing_to_correct_target(target_path, expected_target):
        logger.info(
            'target_already_exists_and_correct_skipping',
            target=str(target_path),
            symlink_name=symlink_name,
        )
        return True

    return False


def resolve_and_create_operation_with_source(
    args: CliArgs,
    install_spec: SourceSpec,
    source_path: Path,
) -> LinkOperation:
    """Create the link operation using an already resolved source path."""
    logger.debug(
        'creating_operation_with_resolved_source',
        path=str(source_path),
    )

    # Create link target
    target = LinkTarget(
        source_path=source_path,
        target_directory=args.directory,
        symlink_name=args.symlink_name,
    )
    logger.debug(
        'created_link_target',
        source_path=str(target.source_path),
        target_directory=target.target_directory,
        symlink_name=target.symlink_name,
        _verbose_target=target.model_dump(mode='json'),
    )

    # Create link operation
    operation = LinkOperation(
        spec=install_spec,
        target=target,
        force=args.force,
        dry_run=args.dry_run,
    )
    logger.debug(
        'created_link_operation',
        symlink_name=operation.symlink_name,
        full_source_path=str(operation.full_source_path),
        _verbose_operation=operation.model_dump(mode='json'),
    )

    return operation


def validate_source_directory(operation: LinkOperation) -> None:
    """Validate that the source directory exists."""
    logger.debug(
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
            logger.debug(  # pragma: no cover - debugging only
                'parent_directory_contents',
                parent=str(parent_dir),
                contents=[str(p) for p in parent_dir.iterdir()],
            )

        error_msg = f'Error: Source directory not found: {operation.full_source_path}\n'
        sys.stderr.write(error_msg)
        sys.exit(1)


def create_symlink_with_logging(
    operation: LinkOperation,
    args: CliArgs,
) -> None:
    """Create the symlink with appropriate logging."""
    target_path = Path.cwd() / operation.symlink_name
    logger.debug(
        'creating_symlink',
        target=str(target_path),
        source=str(operation.full_source_path),
    )

    # If target exists but we got here, it means check_target_exists returned False,
    # indicating the target is incorrect and should be replaced
    force_removal = args.force or target_path.exists()
    create_symlink(
        operation.full_source_path,
        target_path,
        force=force_removal,
    )


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
    validate_source_directory(operation)
    create_symlink_with_logging(operation, args)


def main() -> None:
    """Main entry point for the pkglink CLI."""
    try:
        # Configure logging first (before parsing args in case of errors)
        setup_logging()

        args = parse_args_to_model()

        # Re-configure logging with the correct verbose setting
        setup_logging(args)

        log_startup_info(args)

        install_spec, module_name = determine_install_spec_and_module(args)

        # Handle dry-run early
        handle_dry_run(args, install_spec, module_name)
        if args.dry_run:
            return

        # Resolve source path to check if symlink is correct
        source_path = resolve_source_path(install_spec, module_name)

        # Check if target already exists and points to the correct source
        if check_target_exists(args, install_spec, source_path):
            return

        # Create operation with the already resolved source path
        operation = resolve_and_create_operation_with_source(
            args,
            install_spec,
            source_path,
        )

        # Execute the symlink operation
        execute_symlink_operation(args, operation)

    except Exception as e:
        # Log with safe error representation for YAML serialization
        logger.exception('cli_operation_failed', error=str(e))
        sys.stderr.write(f'Error: {e}\n')
        sys.exit(1)


if __name__ == '__main__':
    main()
