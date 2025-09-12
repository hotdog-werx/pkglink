import argparse
import re
from pathlib import Path

from pkglink.logging import get_logger
from pkglink.models import CliArgs, SourceSpec

logger = get_logger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog='pkglink',
        description='Create symlinks to directories from repositories and Python packages',
    )

    parser.add_argument(
        'source',
        help='Source specification (github:org/repo, package-name, or local path)',
    )
    parser.add_argument(
        'directory',
        nargs='?',
        default='resources',
        help='Directory to link (default: resources)',
    )
    parser.add_argument(
        '--symlink-name',
        help='Custom name for the symlink',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing symlinks',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without doing it',
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging',
    )
    parser.add_argument(
        '--from',
        dest='from_package',
        help='Installable package name (when different from module name)',
    )
    return parser


def parse_args_to_model() -> CliArgs:
    """Parse command line arguments into a typed Pydantic model."""
    parser = create_parser()
    raw_args = parser.parse_args()

    return CliArgs(
        source=raw_args.source,
        directory=raw_args.directory,
        symlink_name=raw_args.symlink_name,
        force=raw_args.force,
        dry_run=raw_args.dry_run,
        verbose=raw_args.verbose,
        from_package=raw_args.from_package,
    )


def determine_install_spec_and_module(args: CliArgs) -> tuple[SourceSpec, str]:
    """Determine what to install and which module to look for based on CLI args."""
    if args.from_package:
        logger.info(
            'using_from_option',
            install_package=args.from_package,
            module_name=args.source,
        )
        install_spec = parse_source(args.from_package)
        logger.debug(
            'parsed_install_spec',
            name=install_spec.name,
            source_type=install_spec.source_type,
            version=install_spec.version,
            _verbose_install_spec=install_spec.model_dump(),
        )

        module_name = args.source
        logger.debug('looking_for_module', module=module_name)
    else:
        logger.info('parsing_source_specification', source=args.source)
        install_spec = parse_source(args.source)
        module_name = install_spec.name
        logger.debug(
            'parsed_source_spec',
            name=install_spec.name,
            source_type=install_spec.source_type,
            version=install_spec.version,
            _verbose_source_spec=install_spec.model_dump(),
        )

    return install_spec, module_name


def parse_source(source: str) -> SourceSpec:
    """Parse a source string into a SourceSpec.

    Supports formats:
    - github:org/repo[@version]
    - package-name[@version]
    - ./local/path or /absolute/path
    """
    if source.startswith('github:'):
        return _parse_github_source(source)

    if _is_local_path(source):
        return SourceSpec(
            source_type='local',
            name=_extract_local_name(source),
            local_path=source,
        )

    return _parse_package_source(source)


def _is_local_path(source: str) -> bool:
    """Check if the source string represents a local path."""
    return (
        source in ('.', './')
        or source.startswith(('./', '/', '~'))
        or Path(source).is_absolute()
        or re.match(r'^[A-Za-z]:[/\\]', source) is not None  # Windows absolute path
    )


def _extract_local_name(source: str) -> str:
    """Extract the directory name from a local path."""
    # Handle Windows paths on non-Windows systems
    if re.match(r'^[A-Za-z]:[/\\]', source):
        return source.replace('\\', '/').split('/')[-1]

    path = Path(source).expanduser()
    # For current directory references, resolve to get the actual name
    if source in ('.', './'):
        return path.resolve().name
    return path.name


def _parse_github_source(source: str) -> SourceSpec:
    """Parse a GitHub source specification."""
    github_match = re.match(r'^github:([^/]+)/([^@/]+)(?:@(.+))?$', source)
    if not github_match:
        msg = f'Invalid source format: {source}'
        raise ValueError(msg)

    org, repo, version = github_match.groups()
    # Validate that org and repo are not empty
    if not org.strip() or not repo.strip():
        msg = f'Invalid source format: {source}'
        raise ValueError(msg)

    return SourceSpec(
        source_type='github',
        name=repo.strip(),
        org=org.strip(),
        version=version.strip() if version else None,
    )


def _parse_package_source(source: str) -> SourceSpec:
    """Parse a package source specification."""
    package_match = re.match(r'^([^@]+)(?:@(.+))?$', source)
    if not package_match:
        msg = f'Invalid source format: {source}'
        raise ValueError(msg)

    name, version = package_match.groups()
    return SourceSpec(
        source_type='package',
        name=name,
        version=version,
    )


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
