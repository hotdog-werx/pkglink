"""Refactored pkglink CLI using shared modules."""

from pkglink.argparse import parse_pkglink_args
from pkglink.cli.common import (
    WorkflowEntry,
    download_phase,
    execution_phase,
    handle_cli_exception,
    planning_phase,
    setup_context_and_validate,
    setup_logging_and_handle_errors,
)
from pkglink.models import PkglinkCliArgs


def run_with_cli_args(cli_args: PkglinkCliArgs) -> None:
    """Execute pkglink workflow given parsed CLI arguments."""
    try:
        # Configure logging
        setup_logging_and_handle_errors(verbose=cli_args.verbose)

        # Setup context and validate
        context = setup_context_and_validate(cli_args)

        entry = WorkflowEntry(context=context)
        entries = [entry]
        download_phase(entries)
        planning_phase(entries)
        execution_phase(entries)

    except Exception as e:  # noqa: BLE001 - broad exception for CLI
        handle_cli_exception(e)


def main() -> None:
    """Main entry point for the pkglink CLI."""
    args = parse_pkglink_args()
    run_with_cli_args(args)


if __name__ == '__main__':
    main()
