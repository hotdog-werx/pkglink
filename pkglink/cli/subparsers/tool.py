"""plk tool subcommand."""

import argparse

from pkglink.cli.pkglinkx import run_with_cli_args as run_pkglinkx
from pkglink.models import PkglinkxCliArgs

from . import _shared


def _build_cli_args(
    namespace: argparse.Namespace,
    verbose: int,
) -> PkglinkxCliArgs:
    return PkglinkxCliArgs(
        source=namespace.source,
        directory=namespace.directory,
        symlink_name=namespace.symlink_name,
        skip_resources=getattr(namespace, 'skip_resources', False),
        verbose=verbose,
        from_package=namespace.from_package,
        project_name=namespace.project_name,
        no_setup=namespace.no_setup,
        force=namespace.force,
        dry_run=namespace.dry_run,
    )


def _handle(namespace: argparse.Namespace) -> int:
    verbose = _shared.resolve_verbose(namespace)
    cli_args = _build_cli_args(namespace, verbose)
    run_pkglinkx(cli_args)
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the tool subcommand."""
    parent = _shared.build_common_parent()
    parser = subparsers.add_parser(
        'tool',
        parents=[parent],
        aliases=['x'],
        help='Prepare a package or repository for execution via uvx',
    )
    _shared.apply_install_arguments(
        parser,
        include_inside=False,
        include_skip_resources=True,
    )
    parser.set_defaults(handler=_handle)
