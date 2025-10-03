"""Common CLI functionality shared between pkglink and pkglinkx."""

import sys
from pathlib import Path
from typing import Any

from hotlog import configure_logging, get_logger

from pkglink.execution_plan import (
    execute_plan,
    generate_execution_plan,
)
from pkglink.models import BaseCliArgs, ExecutionPlan, PkglinkContext
from pkglink.parsing import create_pkglink_context
from pkglink.setup import run_post_install_setup

logger = get_logger(__name__)


def setup_logging_and_handle_errors(*, verbose: int) -> None:
    """Configure logging with appropriate verbosity."""
    configure_logging(verbosity=verbose)


def unified_workflow(
    context: PkglinkContext,
    *,
    cache_dir: Path | None = None,
    dist_info_name: str | None = None,
) -> ExecutionPlan:
    """Unified workflow that generates and optionally executes a plan.

    Args:
        context: The pkglink context
        cache_dir: Optional pre-installed cache directory
        dist_info_name: Optional dist-info name from pre-installation
    """
    # Generate the execution plan (may use uvx to cache/download)
    plan = generate_execution_plan(
        context,
        cache_dir=cache_dir,
        dist_info_name=dist_info_name,
    )

    # Show plan in dry-run mode without executing
    if context.cli_args.dry_run:
        logger.info('dry_run_plan_complete')
        return plan

    # Execute the plan
    execute_plan(plan)

    # After plan execution, run post-install setup unless --no-setup is specified
    if not context.cli_args.no_setup:
        # Use the base_dir and linked_path (target_dir for pkglinkx, cwd for pkglink)
        # For pkglinkx, linked_path is inside .pkglink, but symlinks should be created at project root
        symlink_name = context.resolved_symlink_name
        if context.inside_pkglink:
            linked_path = Path.cwd() / '.pkglink' / symlink_name
            base_dir = Path.cwd()  # Always create setup symlinks at project root
        else:
            linked_path = Path.cwd() / symlink_name
            base_dir = Path.cwd()
        run_post_install_setup(linked_path, base_dir)

    logger.info(
        'workflow_completed',
        total_operations=len(plan.file_operations),
        **context.get_concise_summary(),
    )

    return plan


def handle_cli_exception(e: Exception) -> None:
    """Handle CLI exceptions with consistent logging and exit."""
    logger.exception('cli_operation_failed', error=str(e))
    sys.exit(1)


def setup_context_and_validate(cli_args: BaseCliArgs) -> PkglinkContext:
    """Setup context from CLI args and validate it.

    Args:
        cli_args: Parsed CLI arguments (CliArgs or PkglinkxCliArgs)

    Returns:
        Validated context object
    """
    # Create context object with all necessary information
    context = create_pkglink_context(cli_args)

    # Log starting message (concise summary only)
    cli_name = 'pkglink' if context.is_pkglink_cli else 'pkglinkx'
    start_notice = f'starting_{cli_name}'
    logger.info(start_notice, **context.get_concise_summary())

    # Log detailed information as debug if verbose or if names differ
    if context.cli_args.verbose or context.install_spec.name != context.module_name:
        logger.debug(
            'context_details',
            **context.model_dump_for_logging(),
        )

    # Validate context and log any warnings
    warnings = context.validate_context()
    if warnings:
        for warning in warnings:
            logger.warning('context_validation', message=warning)

    return context


def log_completion(
    context: PkglinkContext,
    execution_plan: ExecutionPlan | None = None,
) -> None:
    """Log completion message for either CLI.

    Args:
        context: The pkglink context
        execution_plan: Optional execution plan with operation count
    """
    if context.cli_args.dry_run:
        return  # Don't log completion for dry runs

    cli_name = 'pkglink' if context.is_pkglink_cli else 'pkglinkx'

    log_data: dict[str, Any] = {
        'display_name': context.get_display_name(),
    }

    if execution_plan:
        log_data['operation_count'] = len(execution_plan.file_operations)

    if context.is_pkglink_cli:
        log_data['inside_pkglink'] = context.inside_pkglink
    elif context.is_pkglinkx_cli:
        # For pkglinkx, add the target directory info
        log_data['target_dir'] = f'.pkglink/{context.install_spec.project_name}'
        log_data['python_module_name'] = context.module_name
        log_data['source_type'] = context.source_type

    msg = f'{cli_name}_completed'
    logger.info(msg, **log_data)

    # Add next steps for pkglinkx
    if context.is_pkglinkx_cli:
        target_dir = f'.pkglink/{context.install_spec.project_name}'
        logger.info('✅ next_steps', run=f'uvx --from {target_dir} <command>')
