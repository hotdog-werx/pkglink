"""pkglink tool subcommand."""

import argparse
from pathlib import Path

import yaml
from hotlog import get_logger

from pkglink.cli.common import (
    WorkflowEntry,
    download_phase,
    execution_phase,
    handle_cli_exception,
    planning_phase,
    setup_context_and_validate,
    setup_logging_and_handle_errors,
)
from pkglink.models import PkglinkContext, PkglinkxCliArgs
from pkglink.uvx import refresh_package

from . import _shared

logger = get_logger(__name__)


def check_version_changed(
    target_dir: Path,
    current_spec: str,
    current_hash: str,
) -> bool:
    """Check if we need to refresh based on version/hash changes."""
    metadata_file = target_dir / '.pkglink-metadata.yaml'

    if not metadata_file.exists():
        logger.debug('no_existing_metadata_refresh_needed')
        return True  # First install

    try:
        with metadata_file.open() as f:
            existing_metadata = yaml.safe_load(f)
    except Exception as e:  # noqa:BLE001 - broad exception to catch all yaml read errors
        logger.warning('failed_to_read_metadata_assuming_changed', error=str(e))
        return True

    existing_hash = existing_metadata.get('source_hash')
    existing_spec = existing_metadata.get('install_spec')
    changed = existing_hash != current_hash or existing_spec != current_spec
    logger.debug(
        'version_change_check',
        changed=changed,
        existing_hash=existing_hash,
        current_hash=current_hash,
    )
    return changed


def setup_pkglinkx_context(
    cli_args: PkglinkxCliArgs,
) -> tuple[PkglinkContext, Path]:
    """Create context for pkglinkx given parsed CLI arguments."""
    # Configure logging and setup context (shared functions)
    setup_logging_and_handle_errors(verbose=cli_args.verbose)
    context = setup_context_and_validate(cli_args)

    # Create .pkglink target directory (pkglinkx-specific)
    pkglink_base = Path('.pkglink')
    target_dir = pkglink_base / context.install_spec.project_name

    return context, target_dir


def handle_version_tracking(
    context: PkglinkContext,
    cache_dir: Path,
    target_dir: Path,
) -> None:
    """Handle version tracking and refresh logic."""
    try:
        current_hash = cache_dir.name.split('_')[-1] if '_' in cache_dir.name else 'unknown'
        current_spec = str(context.install_spec.model_dump())
        needs_refresh = check_version_changed(
            target_dir,
            current_spec,
            current_hash,
        )

        # Force uvx refresh if needed
        if needs_refresh:
            success = refresh_package(
                context.module_name,
                target_dir,
            )
            if success:
                logger.info(
                    'uvx_refresh_successful',
                    package=context.module_name,
                    _display_level=1,
                )
            else:
                logger.warning(
                    'uvx_refresh_failed_but_continuing',
                    package=context.module_name,
                )
    except Exception as e:  # noqa:BLE001 - broad exception to allow CLI to continue
        logger.warning(
            'version_tracking_failed',
            error=str(e),
            display_name=context.get_display_name(),
        )


def run_with_cli_args(cli_args: PkglinkxCliArgs) -> None:
    """Execute pkglinkx workflow given parsed CLI arguments."""
    try:
        # Setup context and target directory
        context, target_dir = setup_pkglinkx_context(cli_args)

        entry = WorkflowEntry(
            context=context,
            metadata={'target_dir': target_dir},
        )
        entries = [entry]

        download_phase(entries)
        planning_phase(entries)

        def _post_execution(work_entry: WorkflowEntry) -> None:
            plan = work_entry.plan
            if plan is None or plan.uvx_cache_dir is None:
                return
            target = work_entry.metadata.get('target_dir', target_dir)
            handle_version_tracking(
                work_entry.context,
                plan.uvx_cache_dir,
                target,
            )

        execution_phase(
            entries,
            post_execution=_post_execution,
        )

    except Exception as e:  # noqa: BLE001 - broad exception for CLI
        handle_cli_exception(e)


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
    run_with_cli_args(cli_args)
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
