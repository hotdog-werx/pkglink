"""Refactored pkglink CLI using shared modules."""

from pkglink.argparse import parse_pkglink_args
from pkglink.cli.common import (
    handle_cli_exception,
    log_completion,
    setup_context_and_validate,
    setup_logging_and_handle_errors,
    unified_workflow,
)


def main() -> None:
    """Main entry point for the pkglink CLI."""
    try:
        # Parse arguments first
        args = parse_pkglink_args()

        # Configure logging
        setup_logging_and_handle_errors(verbose=args.verbose)

        # Setup context and validate
        context = setup_context_and_validate(args)

        # Run the unified workflow
        execution_plan = unified_workflow(context)

        # Log completion
        log_completion(context, execution_plan)

    except Exception as e:  # noqa: BLE001 - broad exception for CLI
        handle_cli_exception(e)


if __name__ == '__main__':
    main()
