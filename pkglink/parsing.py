import re
from pathlib import Path

from hotlog import get_logger

from pkglink.models import (
    BaseCliArgs,
    ParsedSource,
    PkglinkContext,
    SourceSpec,
)

logger = get_logger(__name__)


def parse_source(
    source: ParsedSource,
    project_name: str | None = None,
) -> SourceSpec:
    """Convert a ParsedSource object into a SourceSpec, always setting project_name."""
    # Ensure required fields are present and fallback to empty string if needed
    if source.source_type == 'github':
        return SourceSpec(
            source_type='github',
            name=source.repo or '',
            org=source.org or '',
            version=source.version,
            project_name=project_name or source.repo or '',
        )
    if source.source_type == 'local':
        return SourceSpec(
            source_type='local',
            name=source.name or '',
            local_path=source.local_path or '',
            project_name=project_name or source.name or '',
        )
    # package
    return SourceSpec(
        source_type='package',
        name=source.name or '',
        version=source.version,
        project_name=project_name or source.name or '',
    )


def is_local_path(source: str) -> bool:
    """Check if the source string represents a local path.

    Args:
        source: Source string from CLI

    Returns:
        True if the source is a local path, False otherwise.
    """
    return (
        source in ('.', './')
        or source.startswith(('./', '/', '~'))
        or Path(source).is_absolute()
        or re.match(r'^[A-Za-z]:[/\\]', source) is not None  # Windows absolute path
    )


def extract_local_name(source: str) -> str:
    """Extract the directory name from a local path.

    Args:
        source: Local path string

    Returns:
        The name of the directory at the end of the path.
    """
    # Handle Windows paths on non-Windows systems
    if re.match(r'^[A-Za-z]:[/\\]', source):
        return source.replace('\\', '/').split('/')[-1]

    path = Path(source).expanduser()
    # For current directory references, resolve to get the actual name
    if source in ('.', './'):
        return path.resolve().name
    return path.name


def parse_github_source(value: str) -> tuple[ParsedSource | None, str]:
    """Parse a GitHub source specification.

    Args:
        value: Source string in the format github:org/repo[@version]

    Returns:
        A tuple of (ParsedSource or None, error message string).
    """
    m = re.match(r'^github:([^/]+)/([^@/]+)(?:@(.+))?$', value)
    if not m:
        return None, f'Invalid Github source format: {value}'
    org, repo, version = m.groups()
    if not org.strip() or not repo.strip():
        return None, f'Invalid Github source format: {value}'
    return ParsedSource(
        source_type='github',
        raw=value,
        org=org,
        repo=repo,
        version=version,
        name=repo,
    ), ''


def build_uv_install_spec(spec: SourceSpec) -> str:
    """Build UV install specification from source spec."""
    if spec.source_type == 'github':
        base_url = f'git+https://github.com/{spec.org}/{spec.name}.git'
        return f'{base_url}@{spec.version}' if spec.version else base_url

    if spec.source_type == 'package':
        return f'{spec.name}=={spec.version}' if spec.version else spec.name

    if spec.source_type == 'local':
        # For local sources, resolve the path and return it for uvx installation
        # Use local_path if available, otherwise fall back to name for backwards compatibility
        source_path = spec.local_path or spec.name
        path = Path(source_path).resolve()
        return str(path)

    # next statements should be unreachable since source_type is validated
    msg = f'Unsupported source type: {spec.source_type}'  # pragma: no cover
    raise ValueError(msg)  # pragma: no cover


def create_pkglink_context(args: BaseCliArgs) -> PkglinkContext:
    """Create a comprehensive context object from CLI arguments.

    Simple logic following uvx pattern:
    - source: what module/directory to look for (always)
    - --from: what package to install (when different from source)

    Examples:
        pkglink mymodule                    # Install and look for 'mymodule'
        pkglink --from mypackage mymodule   # Install 'mypackage', look for 'mymodule'

    Args:
        args: CLI arguments from either pkglink or pkglinkx

    Returns:
        PkglinkContext with all necessary information populated
    """
    install_source = args.from_package or args.source
    install_spec = parse_source(install_source, project_name=args.project_name)

    lookup_name = args.source.name if args.from_package else install_spec.name
    normalize = install_spec.source_type in ('github', 'local')
    # Normalize module name for lookup (github/local: hyphens -> underscores)
    module_name = lookup_name.replace('-', '_') if normalize else lookup_name

    logger.debug(
        'parsed_source_spec',
        name=install_spec.name,
        source_type=install_spec.source_type,
        version=install_spec.version,
        module_name=module_name,
        _verbose_source_spec=install_spec.model_dump(),
    )

    return PkglinkContext(
        install_spec=install_spec,
        module_name=module_name,
        cli_args=args,
    )
