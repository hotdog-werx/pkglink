"""Batch pkglink CLI driven by YAML configuration."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from hotlog import add_verbosity_argument, get_logger, resolve_verbosity

from pkglink.cli.common import (
    handle_cli_exception,
    log_completion,
    run_post_install_from_plan,
    setup_logging_and_handle_errors,
)
from pkglink.execution_plan import ExecutionPlan, execute_plan, generate_execution_plan
from pkglink.batch_config import (
    DEFAULT_CONFIG_FILENAME,
    PkglinkConfigError,
    load_batch_contexts,
)
from pkglink.installation import install_with_uvx
from pkglink.models import PkglinkContext

logger = get_logger(__name__)


@dataclass
class BatchEntry:
    """Wrapper around a pkglink context and its execution artefacts."""

    context: PkglinkContext
    cache_dir: Path | None = None
    dist_info_name: str | None = None
    plan: ExecutionPlan | None = None

    @property
    def label(self) -> str:
        return getattr(self.context.cli_args, 'entry_name', self.context.get_display_name())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='pkglink-batch',
        description='Process multiple pkglink entries defined in pkglink.config.yaml',
    )
    parser.add_argument(
        '--config',
        default=DEFAULT_CONFIG_FILENAME,
        help='Path to batch configuration file (default: %(default)s)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Generate plans without executing operations',
    )
    add_verbosity_argument(parser)
    return parser


def _download_phase(entries: list[BatchEntry]) -> None:
    logger.info('batch_download_phase_start', total=len(entries))
    for entry in entries:
        context = entry.context
        logger.info(
            'batch_download_entry_start',
            entry=entry.label,
            install_spec=context.install_spec.model_dump(),
        )
        cache_dir, dist_info_name, _ = install_with_uvx(context.install_spec)
        entry.cache_dir = cache_dir
        entry.dist_info_name = dist_info_name
        logger.info(
            'batch_download_entry_success',
            entry=entry.label,
            cache_dir=str(cache_dir),
            dist_info_name=dist_info_name,
        )
    logger.info('batch_download_phase_complete', succeeded=len(entries))


def _planning_phase(entries: list[BatchEntry]) -> None:
    logger.info('batch_planning_phase_start', total=len(entries))
    for entry in entries:
        context = entry.context
        plan = generate_execution_plan(
            context,
            cache_dir=entry.cache_dir,
            dist_info_name=entry.dist_info_name,
        )
        entry.plan = plan
        logger.info(
            'batch_plan_created',
            entry=entry.label,
            operations=len(plan.file_operations),
        )
    logger.info('batch_planning_phase_complete')


def _execution_phase(entries: list[BatchEntry]) -> None:
    logger.info('batch_execution_phase_start', total=len(entries))
    for entry in entries:
        context = entry.context
        plan = entry.plan
        if plan is None:
            msg = f'Execution plan missing for entry {entry.label}'
            raise RuntimeError(msg)

        if context.cli_args.dry_run:
            logger.info(
                'batch_entry_dry_run',
                entry=entry.label,
                operations=len(plan.file_operations),
            )
            log_completion(context, plan)
            continue

        logger.info('batch_entry_execute', entry=entry.label)
        execute_plan(plan)
        run_post_install_from_plan(plan)
        logger.info(
            'workflow_completed',
            total_operations=len(plan.file_operations),
            **context.get_concise_summary(),
        )
        log_completion(context, plan)
    logger.info('batch_execution_phase_complete')


def main() -> int | None:
    parser = _build_parser()
    args = parser.parse_args()

    verbose = resolve_verbosity(args)
    setup_logging_and_handle_errors(verbose=verbose)

    try:
        config_path = Path(args.config)
        contexts = load_batch_contexts(
            config_path,
            global_verbose=verbose,
            global_dry_run=args.dry_run,
        )
        entries = [BatchEntry(context=context) for context in contexts]

        _download_phase(entries)
        _planning_phase(entries)
        _execution_phase(entries)
        return 0
    except PkglinkConfigError as exc:
        logger.error('batch_configuration_error', error=str(exc))
        handle_cli_exception(exc)
    except Exception as exc:  # noqa: BLE001 - top-level CLI guard
        handle_cli_exception(exc)
    return 0


if __name__ == '__main__':
    main()
