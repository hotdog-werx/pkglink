import hashlib
from pathlib import Path

import yaml
from hotlog import get_logger

from pkglink.installation import (
    find_package_root,
    install_with_uvx,
    resolve_source_path,
)
from pkglink.models import (
    ExecutionPlan,
    FileOperation,
    PackageInfo,
    PkglinkContext,
)
from pkglink.package_discovery import extract_package_metadata
from pkglink.project_structure import generate_pyproject_toml
from pkglink.symlinks import create_symlink

logger = get_logger(__name__)


def _plan_base_directory(context: PkglinkContext, plan: ExecutionPlan) -> Path:
    """Plan base directory creation and return the base path.

    Args:
        context: The pkglink context
        plan: Execution plan to add operations to

    Returns:
        Path to the base directory for operations
    """
    if context.inside_pkglink:
        base_dir = Path.cwd() / '.pkglink'
        plan.add_operation(
            'create_directory',
            target_path=base_dir,
            description="Create .pkglink directory if it doesn't exist",
        )
    else:
        base_dir = Path.cwd()

    return base_dir


def _plan_uvx_structure(
    context: PkglinkContext,
    plan: ExecutionPlan,
    base_dir: Path,
    cache_dir: Path | None,
    dist_info_name: str | None,
) -> None:
    """Plan uvx-compatible structure creation for pkglinkx.

    Args:
        context: The pkglink context
        plan: Execution plan to add operations to
        base_dir: Base directory for operations
        cache_dir: Optional pre-installed cache directory
        dist_info_name: Optional dist-info name from pre-installation
    """
    if not context.inside_pkglink:
        return

    target_dir, src_dir = _plan_uvx_directories(context, plan, base_dir)
    cache_dir, dist_info_name = _plan_uvx_cache(
        context,
        plan,
        cache_dir,
        dist_info_name,
    )
    package_info = _plan_uvx_metadata(plan, cache_dir, dist_info_name)
    _plan_uvx_symlink(context, plan, cache_dir, src_dir)
    _plan_pyproject_file(context, plan, target_dir, package_info)
    _plan_metadata_file(plan, target_dir)


def _plan_uvx_directories(
    context: PkglinkContext,
    plan: ExecutionPlan,
    base_dir: Path,
) -> tuple[Path, Path]:
    target_dir = base_dir / context.install_spec.project_name
    plan.add_operation(
        'create_directory',
        target_path=target_dir,
        description=f'Create target directory for {context.get_display_name()}',
    )
    src_dir = target_dir / 'src'
    plan.add_operation(
        'create_directory',
        target_path=src_dir,
        description='Create src/ directory for uvx compatibility',
    )
    return target_dir, src_dir


def _plan_uvx_cache(
    context: PkglinkContext,
    plan: ExecutionPlan,
    cache_dir: Path | None,
    dist_info_name: str | None,
) -> tuple[Path, str]:
    if cache_dir and dist_info_name:
        logger.debug('using_pre_installed_cache', cache_dir=str(cache_dir))
        plan.uvx_cache_dir = cache_dir
    else:
        cache_dir, dist_info_name, _ = install_with_uvx(context.install_spec)
        plan.uvx_cache_dir = cache_dir
    return cache_dir, dist_info_name


def _plan_uvx_metadata(
    plan: ExecutionPlan,
    cache_dir: Path,
    dist_info_name: str,
) -> PackageInfo:
    package_info = extract_package_metadata(
        cache_dir,
        dist_info_name,
    )
    plan.package_info = package_info
    return package_info


def _plan_uvx_symlink(
    context: PkglinkContext,
    plan: ExecutionPlan,
    cache_dir: Path,
    src_dir: Path,
) -> Path:
    package_source = cache_dir / context.module_name
    if not package_source.exists():
        found = None
        for subdir in cache_dir.rglob(context.module_name):
            if subdir.is_dir():
                found = subdir
                logger.debug(
                    'using_exact_package_dir_from_recursive_search',
                    found=str(found),
                )
                break
        if found:
            package_source = found
        else:
            logger.error(
                'package_source_not_found',
                attempted=str(package_source),
                cache_dir=str(cache_dir),
            )
    package_symlink = src_dir / context.module_name
    plan.add_operation(
        'create_symlink',
        source_path=package_source,
        target_path=package_symlink,
        description=f'Symlink Python module {context.module_name}',
    )
    return package_source


def _plan_pyproject_file(
    context: PkglinkContext,
    plan: ExecutionPlan,
    target_dir: Path,
    package_info: PackageInfo,
) -> None:
    """Plan pyproject.toml file creation.

    Args:
        context: The pkglink context
        plan: Execution plan to add operations to
        target_dir: Target directory for the file
        package_info: Package information for generating content
    """
    project_name = package_info.metadata.get('name', context.module_name)
    pyproject_content = generate_pyproject_toml(
        package_name=project_name,
        python_module_name=context.module_name,
        package_info=package_info,
    )

    # Get first few lines for preview
    content_lines = pyproject_content.split('\n')[:10]
    content_preview = '\n'.join(content_lines) + ('...' if len(content_lines) > 10 else '')

    plan.add_operation(
        'create_file',
        target_path=target_dir / 'pyproject.toml',
        content_preview=content_preview,
        description=f'Generate pyproject.toml with {len(package_info.dependencies or [])} dependencies',
    )


def _plan_metadata_file(plan: ExecutionPlan, target_dir: Path) -> None:
    """Plan metadata file creation.

    Args:
        plan: Execution plan to add operations to
        target_dir: Target directory for the file
    """
    plan.add_operation(
        'create_file',
        target_path=target_dir / '.pkglink-metadata.yaml',
        content_preview='version: ...\nsource_hash: ...\ninstall_spec: ...',
        description='Create metadata file for tracking',
    )


def _plan_resource_symlink(
    context: PkglinkContext,
    plan: ExecutionPlan,
    base_dir: Path,
    cache_dir: Path | None = None,
) -> None:
    """Plan resource symlink creation if not skipped.

    Args:
        context: The pkglink context
        plan: Execution plan to add operations to
        base_dir: Base directory for operations
        cache_dir: Optional cache directory to use (avoids redundant uvx calls)
    """
    if context.skip_resources:
        return

    # Use provided cache or resolve source path (for backward compatibility)
    if cache_dir:
        try:
            package_root = find_package_root(
                cache_dir,
                context.module_name,
                context.cli_args.directory,
            )
        except Exception:
            # For pkglinkx, warn and skip; for pkglink, re-raise
            if context.is_pkglinkx_cli:
                logger.warning(
                    'no_package_subdir_found_skipping_resource_symlink',
                    expected=context.cli_args.directory,
                    install_dir=str(cache_dir),
                    target_subdir=context.cli_args.directory,
                    suggestion='Use --skip-resources to avoid this warning if the package has no resources',
                )
                return
            raise
        resource_source = package_root / context.cli_args.directory
    else:
        # Fallback to resolve_source_path (triggers uvx call)
        source_path = resolve_source_path(
            context.install_spec,
            context.module_name,
        )
        resource_source = source_path / context.cli_args.directory

    if resource_source.exists():
        # Plan resource symlink
        target_path = base_dir / context.resolved_symlink_name
        plan.add_operation(
            'create_symlink',
            source_path=resource_source,
            target_path=target_path,
            description=f'Symlink {context.cli_args.directory}/ directory as {context.resolved_symlink_name}',
        )
    elif context.is_pkglinkx_cli:
        logger.warning(
            'resource_directory_not_found_skipping_in_plan',
            resource_source=str(resource_source),
        )
    else:
        msg = f'Resource directory not found: {resource_source}'
        raise RuntimeError(msg)


def generate_execution_plan(
    context: PkglinkContext,
    cache_dir: Path | None = None,
    dist_info_name: str | None = None,
) -> ExecutionPlan:
    """Generate a complete execution plan for pkglink operations.

    This analyzes what will be created without actually creating anything,
    enabling comprehensive dry-run functionality and better testing.

    Args:
        context: Complete context with all necessary information
        cache_dir: Optional pre-installed cache directory
        dist_info_name: Optional dist-info name from pre-installation

    Returns:
        ExecutionPlan with all operations that would be performed
    """
    plan = ExecutionPlan(context=context)

    logger.debug(
        'generating_execution_plan',
        context_summary=context.get_concise_summary(),
    )

    # Plan base directory creation
    base_dir = _plan_base_directory(context, plan)

    # Plan uvx structure for pkglinkx
    _plan_uvx_structure(context, plan, base_dir, cache_dir, dist_info_name)

    # Plan resource symlink creation - pass cache_dir to avoid redundant uvx calls
    effective_cache_dir = cache_dir
    if not effective_cache_dir and hasattr(plan, 'uvx_cache_dir') and plan.uvx_cache_dir:
        effective_cache_dir = plan.uvx_cache_dir
    _plan_resource_symlink(context, plan, base_dir, effective_cache_dir)

    logger.info('execution_plan_generated', **plan.get_summary())
    return plan


def _execute_create_directory(operation: FileOperation) -> None:
    """Execute a create_directory operation.

    Args:
        operation: FileOperation with operation_type='create_directory'
    """
    operation.target_path.mkdir(parents=True, exist_ok=True)
    logger.debug(
        'created_directory',
        path=str(operation.target_path),
    )


def _execute_create_symlink(operation: FileOperation) -> None:
    """Execute a create_symlink operation using robust symlink logic."""
    if operation.source_path is None:
        msg = f'Source path required for symlink operation: {operation}'
        raise ValueError(msg)

    # Use robust symlink creation logic
    create_symlink(
        source=operation.source_path,
        target=operation.target_path,
        force=True,  # Always force removal if target exists
    )


def _generate_pyproject_content(plan: ExecutionPlan) -> str:
    """Generate pyproject.toml content from execution plan.

    Args:
        plan: ExecutionPlan containing package info and context

    Returns:
        Generated pyproject.toml content as string

    Raises:
        ValueError: If package info is missing
    """
    if plan.package_info is None:
        msg = 'Package info required for pyproject.toml generation'
        raise ValueError(msg)

    project_name = plan.package_info.metadata.get(
        'name',
        plan.context.module_name,
    )
    return generate_pyproject_toml(
        package_name=project_name,
        python_module_name=plan.context.module_name,
        package_info=plan.package_info,
    )


def _generate_metadata_content(plan: ExecutionPlan) -> dict:
    """Generate metadata content for .pkglink-metadata.yaml.

    Args:
        plan: ExecutionPlan containing context and package info

    Returns:
        Dictionary with metadata content
    """
    spec_str = f'{plan.context.install_spec.source_type}:{plan.context.install_spec.name}'
    if plan.context.install_spec.org:
        spec_str = (
            f'{plan.context.install_spec.source_type}:{plan.context.install_spec.org}/{plan.context.install_spec.name}'
        )
    if plan.context.install_spec.version:
        spec_str += f'@{plan.context.install_spec.version}'
    source_hash = hashlib.md5(spec_str.encode()).hexdigest()[:8]  # noqa: S324

    return {
        'version': plan.package_info.version if plan.package_info else 'unknown',
        'source_hash': source_hash,
        'install_spec': str(plan.context.install_spec.model_dump()),
        'package_name': plan.context.module_name,
        'console_scripts': plan.package_info.console_scripts if plan.package_info else {},
        'dependencies': plan.package_info.dependencies or [] if plan.package_info else [],
        'last_refreshed': str(Path().cwd()),
    }


def _execute_create_file(operation: FileOperation, plan: ExecutionPlan) -> None:
    """Execute a create_file operation.

    Args:
        operation: FileOperation with operation_type='create_file'
        plan: ExecutionPlan for generating file content
    """
    if 'pyproject.toml' in str(operation.target_path):
        content = _generate_pyproject_content(plan)
        operation.target_path.write_text(content)

    elif '.pkglink-metadata.yaml' in str(operation.target_path):
        metadata = _generate_metadata_content(plan)
        with operation.target_path.open('w') as f:
            yaml.dump(metadata, f, default_flow_style=False)
    else:
        logger.warning(  # pragma: no cover - defensive, only if new file types are added
            'no_content_for_file_operation',
            path=str(operation.target_path),
        )

    logger.debug('created_file', path=str(operation.target_path))


def execute_plan(plan: ExecutionPlan) -> None:
    """Execute the operations in an execution plan.

    Args:
        plan: ExecutionPlan to execute
    """
    # Dispatch map for operation types
    operation_handlers = {
        'create_directory': lambda op, _: _execute_create_directory(op),
        'create_symlink': lambda op, _: _execute_create_symlink(op),
        'create_file': lambda op, p: _execute_create_file(op, p),
    }

    for operation in plan.file_operations:
        handler = operation_handlers[operation.operation_type]
        handler(operation, plan)
