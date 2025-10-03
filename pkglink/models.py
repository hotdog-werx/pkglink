from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints


class PackageInfo(BaseModel):
    """Information extracted from a package's dist-info directory."""

    version: str
    console_scripts: dict[str, str] = {}
    metadata: dict[str, str] = {}
    dependencies: list[str] = []


class ParsedSource(BaseModel):
    """Intermediate validated source info for CLI parsing."""

    source_type: Literal['github', 'package', 'local']
    name: str
    raw: str
    org: str | None = None
    repo: str | None = None
    version: str | None = None
    # For local sources
    local_path: str | None = None


class SourceSpec(BaseModel):
    """Represents a parsed source specification."""

    source_type: Literal['github', 'package', 'local']
    name: Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
    version: str | None = None
    org: str | None = None  # For GitHub sources
    local_path: str | None = None  # For local sources, stores the original path
    project_name: Annotated[
        str,
        StringConstraints(min_length=1, strip_whitespace=True),
    ]  # Required project name


class LinkTarget(BaseModel):
    """Represents the target for a symlink operation."""

    model_config = ConfigDict(
        # Serialize Path objects as strings
        json_encoders={Path: str},
    )

    source_path: Path
    target_directory: Annotated[
        str,
        StringConstraints(min_length=1, strip_whitespace=True),
    ] = 'resources'
    symlink_name: str | None = None


class LinkOperation(BaseModel):
    """Represents a complete link operation."""

    model_config = ConfigDict(
        # Serialize Path objects as strings
        json_encoders={Path: str},
    )

    spec: SourceSpec
    target: LinkTarget
    force: bool = False
    dry_run: bool = False


class BaseCliArgs(BaseModel):
    """Base command line arguments model with common fields."""

    source: ParsedSource  # Validated source spec (github, package, or local)
    directory: str = 'resources'  # Target directory name within the package
    symlink_name: str | None = None  # Custom name for the symlink (defaults to .{source})
    verbose: int = 0  # Enable verbose logging output
    from_package: ParsedSource | None = None  # Install from PyPI package, GitHub repo, or local path
    project_name: str | None = None  # For GitHub repos with different PyPI package names
    no_setup: bool = False  # Skip post-install setup steps
    force: bool = False  # Overwrite existing symlinks/directories
    dry_run: bool = False  # Show what would be done without executing


class PkglinkCliArgs(BaseCliArgs):
    """Command line arguments model for pkglink CLI."""

    skip_resources: bool = False
    inside_pkglink: bool = False


class PkglinkxCliArgs(BaseCliArgs):
    """Command line arguments model for pkglinkx CLI."""

    skip_resources: bool = False


class PkglinkxMetadata(BaseModel):
    """Metadata for pkglinkx installations."""

    version: str
    source_hash: str
    install_spec: str
    package_name: str
    console_scripts: dict[str, str] = {}
    last_refreshed: str


class PkglinkContext(BaseModel):
    """Context object for pkglink operations.

    Simple model following uvx pattern:
    - install_spec: what to install (package/repo)
    - module_name: what module/directory to look for
    - cli_args: the original CLI arguments (CliArgs or PkglinkxCliArgs)
    """

    # What to install
    install_spec: SourceSpec

    # What module/directory to look for
    module_name: str

    # Original CLI arguments - keep reference to determine CLI type and access fields
    cli_args: BaseCliArgs

    @property
    def skip_resources(self) -> bool:
        """Get the skip resources flag (pkglinkx only)."""
        return getattr(self.cli_args, 'skip_resources', False)

    @property
    def inside_pkglink(self) -> bool:
        """Get the inside pkglink flag (pkglink only). pkglinkx always works inside .pkglink."""
        if self.is_pkglinkx_cli:
            return True  # pkglinkx always works inside .pkglink
        return getattr(self.cli_args, 'inside_pkglink', False)

    @property
    def is_pkglink_cli(self) -> bool:
        """Check if this is from the pkglink CLI."""
        return isinstance(self.cli_args, PkglinkCliArgs)

    @property
    def is_pkglinkx_cli(self) -> bool:
        """Check if this is from the pkglinkx CLI."""
        return isinstance(self.cli_args, PkglinkxCliArgs)

    @property
    def resolved_symlink_name(self) -> str:
        """Get the final symlink name."""
        # If CLI provides a symlink name, use it
        if self.cli_args.symlink_name:
            return self.cli_args.symlink_name
        # For GitHub sources, default to repo name (install_spec.name)
        if self.source_type in ('github', 'local'):
            return f'.{self.install_spec.name}'
        # Otherwise, use .{module_name}
        return f'.{self.module_name}'

    @property
    def source_type(self) -> str:
        """Get the source type (github, package, local)."""
        return self.install_spec.source_type

    def get_display_name(self) -> str:
        """Get a human-readable display name for logging."""
        if self.source_type == 'github':
            return f'{self.install_spec.org}/{self.install_spec.name}'
        if self.source_type == 'local':
            return f'local:{self.install_spec.local_path or self.install_spec.name}'
        return self.install_spec.name

    def model_dump_for_logging(self) -> dict:
        """Get a dict suitable for verbose logging."""
        return {
            'source_type': self.source_type,
            'module_name': self.module_name,
            'resolved_symlink_name': self.resolved_symlink_name,
            'display_name': self.get_display_name(),
            'skip_resources': self.skip_resources,
            'inside_pkglink': self.inside_pkglink,
            'cli_type': 'pkglink' if self.is_pkglink_cli else 'pkglinkx',
            'install_spec': self.install_spec.model_dump(),
            'cli_args': self.cli_args.model_dump(),
        }

    def get_concise_summary(self) -> dict:
        """Get a concise summary for normal logging (not verbose)."""
        base = {
            'display_name': self.get_display_name(),
            'source_type': self.source_type,
            'target_directory': self.cli_args.directory,
            'dry_run': self.cli_args.dry_run,
            'cli_type': 'pkglink' if self.is_pkglink_cli else 'pkglinkx',
        }

        # Only include names if they're different (interesting case)
        if self.install_spec.name != self.module_name:
            base.update(
                {
                    'install_spec': self.install_spec.name,
                    'lookup_module': self.module_name,
                    'note': 'Installing different package than lookup module',
                },
            )

        return base

    def validate_context(self) -> list[str]:
        """Validate the context and return any warnings or issues.

        Note: Only call this after dist-info lookup has succeeded.
        If dist-info is missing, actionable errors are handled earlier in the workflow.
        """
        warnings = []

        # Normalize names for comparison
        normalized_module = self.module_name.replace('-', '_').lower()
        normalized_repo = self.install_spec.name.replace('-', '_').lower()
        repo_type = {'github': 'GitHub repo', 'local': 'local project'}.get(
            self.source_type,
            self.source_type,
        )

        # Check for repo/module mismatch only if normalization does not resolve it
        nonpackage = self.source_type in ('github', 'local')
        name_mismatch = self.install_spec.name != self.module_name
        if nonpackage and name_mismatch and normalized_repo != normalized_module:
            warnings.append(
                f'{repo_type} "{self.install_spec.name}" differs from lookup module "{self.module_name}". '
                'This may indicate a packaging or lookup issue.',
            )

        return warnings


class FileOperation(BaseModel):
    """Represents a file operation to be performed."""

    operation_type: Literal['create_file', 'create_symlink', 'create_directory']
    source_path: Path | None = None  # For symlinks
    target_path: Path
    content_preview: str | None = None  # For file creation, first few lines
    description: str


class ExecutionPlan(BaseModel):
    """Complete execution plan for pkglink operations."""

    model_config = ConfigDict(
        json_encoders={Path: str},
    )

    context: PkglinkContext
    file_operations: list[FileOperation] = []
    uvx_cache_dir: Path | None = None
    package_info: PackageInfo | None = None

    def add_operation(
        self,
        operation_type: Literal[
            'create_file',
            'create_symlink',
            'create_directory',
        ],
        target_path: Path,
        source_path: Path | None = None,
        content_preview: str | None = None,
        description: str = '',
    ) -> None:
        """Add a file operation to the plan."""
        operation = FileOperation(
            operation_type=operation_type,
            source_path=source_path,
            target_path=target_path,
            content_preview=content_preview,
            description=description,
        )
        self.file_operations.append(operation)

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the execution plan."""
        ops_by_type = {}
        for op in self.file_operations:
            if op.operation_type not in ops_by_type:
                ops_by_type[op.operation_type] = []
            ops_by_type[op.operation_type].append(str(op.target_path))

        return {
            'total_operations': len(self.file_operations),
            'operations_by_type': ops_by_type,
            'context_summary': self.context.get_concise_summary(),
        }
