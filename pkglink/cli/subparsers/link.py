"""pkglink link subcommand."""

import argparse

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

from . import _shared


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


def _build_cli_args(
    namespace: argparse.Namespace,
    verbose: int,
) -> PkglinkCliArgs:
    return PkglinkCliArgs(
        source=namespace.source,
        directory=namespace.directory,
        symlink_name=namespace.symlink_name,
        verbose=verbose,
        from_package=namespace.from_package,
        project_name=namespace.project_name,
        no_setup=namespace.no_setup,
        force=namespace.force,
        dry_run=namespace.dry_run,
        skip_resources=getattr(namespace, 'skip_resources', False),
        inside_pkglink=getattr(namespace, 'inside', False),
    )


def _handle(namespace: argparse.Namespace) -> int:
    verbose = _shared.resolve_verbose(namespace)
    cli_args = _build_cli_args(namespace, verbose)
    run_with_cli_args(cli_args)
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the link subcommand."""
    parent = _shared.build_common_parent()
    parser = subparsers.add_parser(
        'link',
        parents=[parent],
        aliases=['ln'],
        help='Link a package or repository into the current project',
    )
    _shared.apply_install_arguments(
        parser,
        include_inside=True,
        include_skip_resources=True,
    )
    parser.set_defaults(handler=_handle)
