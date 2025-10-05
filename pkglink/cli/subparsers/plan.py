"""plk plan subcommand."""

import argparse

from pkglink.cli.pkglinkx import run_with_cli_args as run_pkglinkx
from pkglink.cli.subparsers.link import run_with_cli_args as run_pkglink
from pkglink.models import PkglinkCliArgs, PkglinkxCliArgs

from . import _shared


def _build_link_args(
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
        dry_run=True,
        skip_resources=getattr(namespace, 'skip_resources', False),
        inside_pkglink=getattr(namespace, 'inside', False),
    )


def _build_tool_args(
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
        dry_run=True,
    )


def _handle(namespace: argparse.Namespace) -> int:
    verbose = _shared.resolve_verbose(namespace)
    if namespace.tool_mode:
        cli_args = _build_tool_args(namespace, verbose)
        run_pkglinkx(cli_args)
    else:
        cli_args = _build_link_args(namespace, verbose)
        run_pkglink(cli_args)
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the plan subcommand."""
    parent = _shared.build_common_parent()
    parser = subparsers.add_parser(
        'plan',
        parents=[parent],
        aliases=['preview'],
        help='Generate plans without executing any operations',
    )
    _shared.apply_install_arguments(
        parser,
        include_inside=True,
        include_skip_resources=True,
    )
    parser.add_argument(
        '--tool',
        dest='tool_mode',
        action='store_true',
        help='Plan operations using the tool workflow instead of link',
    )
    parser.set_defaults(handler=_handle)
