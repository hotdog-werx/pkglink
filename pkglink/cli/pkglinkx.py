"""Enhanced pkglinkx CLI supporting GitHub, PyPI, and local sources."""

from pathlib import Path

import yaml
from hotlog import get_logger

from pkglink.argparse import parse_pkglinkx_args
from pkglink.cli.common import (
    handle_cli_exception,
    log_completion,
    setup_context_and_validate,
    setup_logging_and_handle_errors,
    unified_workflow,
)
from pkglink.installation import install_with_uvx
from pkglink.models import PkglinkContext
from pkglink.uvx import refresh_package

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


def setup_pkglinkx_context() -> tuple[PkglinkContext, Path]:
    """Parse arguments and create context for pkglinkx.

    Returns:
        Tuple of (context, target_directory)
    """
    # Parse arguments
    cli_args = parse_pkglinkx_args()

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


def main() -> None:
    """Main entry point for the pkglinkx CLI."""
    try:
        # Setup context and target directory
        context, target_dir = setup_pkglinkx_context()

        # Install and validate early to get package info for pyproject.toml generation
        cache_dir, dist_info_name, _ = install_with_uvx(context.install_spec)

        # Run the unified workflow which handles both uvx structure and resource symlinks
        # Pass the pre-installed cache to avoid duplicate installation
        execution_plan = unified_workflow(
            context,
            cache_dir=cache_dir,
            dist_info_name=dist_info_name,
        )

        # Skip post-processing in dry-run mode
        if context.cli_args.dry_run:
            return

        # Handle version tracking and refresh (only if uvx install succeeded)
        if execution_plan.uvx_cache_dir:
            handle_version_tracking(
                context,
                execution_plan.uvx_cache_dir,
                target_dir,
            )

        # Log completion
        log_completion(context, execution_plan)

    except Exception as e:  # noqa: BLE001 - broad exception for CLI
        handle_cli_exception(e)


if __name__ == '__main__':
    main()
