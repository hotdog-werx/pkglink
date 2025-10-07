"""Common CLI functionality shared across pkglink CLIs."""

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hotlog import configure_logging, get_logger
from hotlog.live import LiveLogger, maybe_live_logging

from pkglink.execution_plan import execute_plan, generate_execution_plan
from pkglink.installation import install_with_uvx
from pkglink.models import BaseCliArgs, ExecutionPlan, PkglinkContext
from pkglink.parsing import create_pkglink_context
from pkglink.setup import run_post_install_setup
from pkglink.version import __version__

logger = get_logger(__name__)


def _build_completion_log_data(
    context: PkglinkContext,
    execution_plan: ExecutionPlan | None = None,
) -> dict[str, Any]:
    """Create the payload dict used when logging completion messages."""
    log_data: dict[str, Any] = {
        '_verbose_display_name': context.get_display_name(),
        '_verbose_canonical_source': context.canonical_source,
        '_verbose_primary_target': context.primary_target_display,
    }
    if execution_plan:
        log_data['_verbose_operation_count'] = len(
            execution_plan.file_operations,
        )

    if context.is_pkglink_cli:
        log_data['_verbose_inside_pkglink'] = context.inside_pkglink
    elif context.is_pkglinkx_cli:
        log_data['_verbose_target_dir'] = f'.pkglink/{context.install_spec.project_name}'
        log_data['_verbose_python_module_name'] = context.module_name
        log_data['_verbose_source_type'] = context.source_type

    if context.is_batch_cli:
        log_data['_verbose_config_entry'] = getattr(
            context.cli_args,
            'entry_name',
            'unknown',
        )
        config_path = getattr(context.cli_args, 'config_path', None)
        if config_path:
            log_data['_verbose_config_path'] = config_path

    return log_data


def _log_next_steps_for_pkglinkx(context: PkglinkContext) -> None:
    """Log helpful next-step guidance for pkglinkx runs."""
    target_dir = f'.pkglink/{context.install_spec.project_name}'
    logger.info('✅ next_steps', run=f'uvx --from {target_dir} <command>')


@dataclass
class WorkflowEntry:
    """Wrapper around a pkglink context and its execution artefacts."""

    context: PkglinkContext
    cache_dir: Path | None = None
    dist_info_name: str | None = None
    plan: ExecutionPlan | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        """Get a human-readable label for this entry."""
        return getattr(
            self.context.cli_args,
            'entry_name',
            self.context.get_display_name(),
        )


def setup_logging_and_handle_errors(*, verbose: int) -> None:
    """Configure logging with appropriate verbosity."""
    configure_logging(verbosity=verbose)
    logger.info(
        'pkglink_initialized',
        _verbose_pkglink_version=__version__,
        _display_level=1,
    )


def run_post_install_from_plan(plan: ExecutionPlan) -> list[dict[str, str]]:
    """Run post-install setup steps based on an execution plan."""
    context = plan.context
    if context.cli_args.no_setup:
        return []

    symlink_name = context.resolved_symlink_name
    if context.inside_pkglink:
        linked_path = Path.cwd() / '.pkglink' / symlink_name
        base_dir = Path.cwd()
    else:
        linked_path = Path.cwd() / symlink_name
        base_dir = Path.cwd()

    return run_post_install_setup(linked_path, base_dir)


def download_phase(entries: list[WorkflowEntry]) -> None:
    """Download required packages for all entries."""
    logger.info(
        'download_phase_start',
        total=len(entries),
        _display_level=1,
    )

    with maybe_live_logging('Downloading packages...') as live:
        for entry in entries:
            context = entry.context

            if live is not None:
                live.info('downloading_entry', entry=entry.label)
            else:
                logger.info(
                    'download_entry_start',
                    entry=entry.label,
                    _display_level=1,
                    _verbose_install_spec=context.install_spec.model_dump(),
                )

            cache_dir, dist_info_name, _ = install_with_uvx(
                context.install_spec,
            )
            entry.cache_dir = cache_dir
            entry.dist_info_name = dist_info_name

            if live is not None:
                live.info('downloaded_entry', entry=entry.label)
            else:
                logger.info(
                    'download_entry_success',
                    entry=entry.label,
                    _display_level=1,
                    _verbose_cache_dir=str(cache_dir),
                    dist_info_name=dist_info_name,
                )

    logger.info(
        'download_phase_complete',
        succeeded=len(entries),
        _display_level=1,
    )


def planning_phase(entries: list[WorkflowEntry]) -> None:
    """Generate execution plans for all entries."""
    logger.info(
        'planning_phase_start',
        total=len(entries),
        _display_level=1,
    )

    with maybe_live_logging('Planning operations...') as live:
        for entry in entries:
            context = entry.context
            plan = generate_execution_plan(
                context,
                cache_dir=entry.cache_dir,
                dist_info_name=entry.dist_info_name,
            )
            entry.plan = plan

            if live is not None:
                live.info(
                    'planned_entry',
                    entry=entry.label,
                    operations=len(plan.file_operations),
                )
            else:
                logger.info(
                    'plan_created',
                    entry=entry.label,
                    operations=len(plan.file_operations),
                    _display_level=1,
                )

    logger.info('planning_phase_complete', _display_level=1)


def _get_execution_plan(entry: WorkflowEntry) -> ExecutionPlan:
    plan = entry.plan
    if plan is None:
        msg = f'Execution plan missing for entry {entry.label}'
        raise RuntimeError(msg)
    return plan


def _process_entry(
    entry: WorkflowEntry,
    live: LiveLogger | None,
    post_execution: Callable[[WorkflowEntry], None] | None,
    completed_entries: dict[str, dict[str, Any]],
) -> None:
    """Process a single entry: dry-run handling, start logging, execute plan.

    Extracted to reduce cyclomatic complexity in `execution_phase`.
    """
    plan = _get_execution_plan(entry)

    dry_run_info = _handle_dry_run(live=live, entry=entry, plan=plan)
    if dry_run_info is not None:
        # Handle key collision for dry-run entries too
        key = entry.label
        if key in completed_entries:
            counter = 2
            while f'{key}_{counter}' in completed_entries:
                counter += 1
            key = f'{key}_{counter}'
        completed_entries[key] = dry_run_info
        return

    _log_execution_start(live=live, entry=entry, plan=plan)

    entry_result = _run_execution(
        entry=entry,
        plan=plan,
        post_execution=post_execution,
    )

    # Handle key collisions by appending a counter
    key = entry.label
    if key in completed_entries:
        counter = 2
        while f'{key}_{counter}' in completed_entries:
            counter += 1
        key = f'{key}_{counter}'

    completed_entries[key] = entry_result


def _emit_final_summary(
    entries_list: list[WorkflowEntry],
    completed_entries: dict[str, dict[str, Any]],
) -> None:
    """Emit aggregate completion message and pkglinkx next steps if applicable.

    Extracted to reduce cyclomatic complexity in `execution_phase`.
    """
    if not completed_entries:
        return

    total_packages = len(completed_entries)

    # Check if this is a dry-run
    is_dry_run = any(entry.get('dry_run', False) for entry in completed_entries.values())

    if is_dry_run:
        message = f'would link {total_packages} package'
        if total_packages != 1:
            message += 's'
        logger.info(message, **completed_entries)
    else:
        message = f'linked {total_packages} package'
        if total_packages != 1:
            message += 's'
        logger.info(message, **completed_entries)

        # Show next steps for pkglinkx after summary (only for real runs)
        if entries_list and entries_list[0].context.is_pkglinkx_cli:
            _log_next_steps_for_pkglinkx(entries_list[0].context)


def _handle_dry_run(
    *,
    live: LiveLogger | None,
    entry: WorkflowEntry,
    plan: ExecutionPlan,
) -> dict[str, Any] | None:
    """Handle dry-run mode.

    Returns:
        Dict with dry-run info if dry-run is enabled, None otherwise.
    """
    context = entry.context
    if not context.cli_args.dry_run:
        return None

    # Log individual dry-run entries at display level 1 (hidden at v0)
    if live is not None:
        live.info(
            'dry_run_entry',
            entry=entry.label,
            operations=len(plan.file_operations),
        )
    else:
        logger.info(
            'entry_dry_run',
            entry=entry.label,
            operations=len(plan.file_operations),
            _display_level=1,
        )

    # Log completion at display level 1 (hidden at v0) so only final summary shows
    logger.info(
        'dry_run_plan_complete',
        entry=entry.label,
        operations=len(plan.file_operations),
        _verbose_cli=context.cli_label,
        _display_level=1,
    )

    # Return dry-run summary info (omit operations count - always 7 for inside_pkglink
    # and doesn't include post-install additional symlinks which are unknown until execution)
    return {
        'source': context.canonical_source,
        'target': context.primary_target_display,
        'dry_run': True,
    }


def _log_execution_start(
    *,
    live: LiveLogger | None,
    entry: WorkflowEntry,
    plan: ExecutionPlan,
) -> None:
    if live is not None:
        live.info(
            'executing_entry',
            entry=entry.label,
            operations=len(plan.file_operations),
        )
        return

    logger.info(
        'entry_execute',
        entry=entry.label,
        _display_level=1,
    )


def _run_execution(
    *,
    entry: WorkflowEntry,
    plan: ExecutionPlan,
    post_execution: Callable[[WorkflowEntry], None] | None,
) -> dict[str, Any]:
    execute_plan(plan)
    additional_symlinks = run_post_install_from_plan(plan)
    context = entry.context
    summary = context.get_concise_summary()
    if plan.package_info and plan.package_info.version:
        summary['version'] = plan.package_info.version
    package_version = summary.get('version')
    logger.info(
        'workflow_completed',
        total_operations=len(plan.file_operations),
        _display_level=1,
        **summary,
    )
    log_completion(context, plan)

    if post_execution:
        post_execution(entry)

    entry_summary: dict[str, Any] = {
        'source': context.canonical_source,
        'target': context.primary_target_display,
    }
    if package_version:
        entry_summary['version'] = package_version
    if additional_symlinks:
        entry_summary['additional'] = additional_symlinks

    # Add CLI usage for packages installed in .pkglink directory
    if context.inside_pkglink:
        target_dir = f'.pkglink/{context.install_spec.project_name}'
        entry_summary['cli_usage'] = f'uvx --from {target_dir} <command>'

    return entry_summary


def execution_phase(
    entries: list[WorkflowEntry],
    *,
    post_execution: Callable[[WorkflowEntry], None] | None = None,
) -> None:
    """Execute previously generated plans for all entries."""
    logger.info(
        'execution_phase_start',
        total=len(entries),
        _display_level=1,
    )

    completed_entries: dict[str, dict[str, Any]] = {}

    with maybe_live_logging('Applying operations...') as live:
        for entry in entries:
            _process_entry(entry, live, post_execution, completed_entries)

    logger.info('execution_phase_complete', _display_level=1)

    _emit_final_summary(entries, completed_entries)


def handle_cli_exception(e: Exception) -> None:
    """Handle CLI exceptions with consistent logging and exit."""
    logger.error('cli_operation_failed', error=str(e))
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
    cli_name = context.cli_label
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

    log_data = _build_completion_log_data(context, execution_plan)
    logger.info('link_completed', _display_level=1, **log_data)
