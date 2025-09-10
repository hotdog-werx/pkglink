import argparse
import logging
import re
from pathlib import Path

from pkglink.models import CliArgs, SourceSpec

logger = logging.getLogger(__name__)


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
            'Using --from: installing %s but looking for module %s',
            args.from_package,
            args.source,
        )
        install_spec = parse_source(args.from_package)
        logger.info('Parsed install spec: %s', install_spec)

        module_name = args.source
        logger.info('Will look for module: %s', module_name)
    else:
        logger.info(
            'Normal mode: parsing source specification: %s',
            args.source,
        )
        install_spec = parse_source(args.source)
        module_name = install_spec.name
        logger.info('Parsed source spec: %s', install_spec)

    return install_spec, module_name


def parse_source(source: str) -> SourceSpec:
    """Parse a source string into a SourceSpec.

    Supports formats:
    - github:org/repo[@version]
    - package-name[@version]
    - ./local/path or /absolute/path
    """
    # Check for malformed GitHub patterns first
    if source.startswith('github:'):
        # GitHub format: github:org/repo[@version]
        github_match = re.match(r'^github:([^/]+)/([^@/]+)(?:@(.+))?$', source)
        if github_match:
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
        # Invalid GitHub format
        msg = f'Invalid source format: {source}'
        raise ValueError(msg)

    # Local path format: starts with ./ or / or ~
    if source.startswith(('./', '/', '~')):
        path = Path(source).expanduser()
        return SourceSpec(
            source_type='local',
            name=path.name,
        )

    # Package format: package-name[@version]
    package_match = re.match(r'^([^@]+)(?:@(.+))?$', source)
    if package_match:
        name, version = package_match.groups()
        return SourceSpec(
            source_type='package',
            name=name,
            version=version,
        )

    msg = f'Invalid source format: {source}'
    raise ValueError(msg)


def build_uv_install_spec(spec: SourceSpec) -> str:
    """Build UV install specification from source spec."""
    if spec.source_type == 'github':
        base_url = f'git+https://github.com/{spec.org}/{spec.name}.git'
        return f'{base_url}@{spec.version}' if spec.version else base_url

    if spec.source_type == 'package':
        return f'{spec.name}=={spec.version}' if spec.version else spec.name

    msg = f'Cannot build UV spec for local source: {spec.name}'
    raise ValueError(msg)
