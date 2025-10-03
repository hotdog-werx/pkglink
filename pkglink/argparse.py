import argparse
import re

from hotlog import add_verbosity_argument, resolve_verbosity

from pkglink.models import (
    ParsedSource,
    PkglinkCliArgs,
    PkglinkxCliArgs,
)
from pkglink.parsing import (
    extract_local_name,
    is_local_path,
    parse_github_source,
)
from pkglink.version import __version__


def argparse_directory(directory: str) -> str:
    """Verify that a directory argument is a relative path.

    Args:
        directory: Directory string from CLI

    Returns:
        The same directory string if valid
    """
    if directory.startswith('/'):
        msg = f'Target directory must be relative path, not absolute: {directory}'
        raise argparse.ArgumentTypeError(msg)
    return directory


def argparse_source(value: str) -> ParsedSource:
    """Argparse type for validated source argument."""
    if value.startswith('github:'):
        # Validate Github source format
        result, error = parse_github_source(value)
        if not result:
            raise argparse.ArgumentTypeError(error)
        return result
    if is_local_path(value):
        # Accept as local path
        name = extract_local_name(value)
        return ParsedSource(
            source_type='local',
            raw=value,
            local_path=value,
            name=name,
        )
    # Accept as package
    package_match = re.match(r'^([^@]+)(?:@(.+))?$', value)
    if not package_match:
        msg = f'Invalid pypi package source format: {value}'
        raise argparse.ArgumentTypeError(msg)
    name, version = package_match.groups()
    return ParsedSource(
        source_type='package',
        raw=value,
        name=name,
        version=version,
    )


def create_base_parser(
    prog_name: str,
    description: str,
) -> argparse.ArgumentParser:
    """Create a base argument parser with common arguments for both CLIs.

    Args:
        prog_name: Name of the program (pkglink or pkglinkx)
        description: Description for the CLI

    Returns:
        ArgumentParser with common arguments added
    """
    parser = argparse.ArgumentParser(
        prog=prog_name,
        description=description,
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'{prog_name} {__version__}',
    )
    parser.add_argument(
        'source',
        type=argparse_source,
        help='Source specification (github:org/repo, package-name, or local path)',
    )
    parser.add_argument(
        'directory',
        nargs='?',
        default='resources',
        type=argparse_directory,
        help='Directory to link (default: resources)',
    )
    parser.add_argument(
        '--symlink-name',
        help='Custom name for the symlink',
    )
    add_verbosity_argument(parser)
    parser.add_argument(
        '--from',
        dest='from_package',
        type=argparse_source,
        help='Installable package name (when different from module name)',
    )
    parser.add_argument(
        '--project-name',
        dest='project_name',
        help='PyPI project name (for GitHub repos with different package names)',
    )
    parser.add_argument(
        '--no-setup',
        action='store_true',
        help='Skip running post-install setup (pkglink.yaml)',
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

    return parser


def parse_pkglink_args() -> PkglinkCliArgs:
    """Create the argument parser for pkglink."""
    parser = create_base_parser(
        prog_name='pkglink',
        description='Create symlinks to directories from repositories and Python packages',
    )

    # Add pkglink-specific arguments
    parser.add_argument(
        '--inside-pkglink',
        action='store_true',
        help='Create symlink inside .pkglink directory instead of current directory',
    )
    raw_args = parser.parse_args()
    return PkglinkCliArgs(
        source=raw_args.source,
        directory=raw_args.directory,
        symlink_name=raw_args.symlink_name,
        force=raw_args.force,
        dry_run=raw_args.dry_run,
        verbose=resolve_verbosity(raw_args),
        from_package=raw_args.from_package,
        project_name=raw_args.project_name,
        no_setup=raw_args.no_setup,
        inside_pkglink=raw_args.inside_pkglink,
    )


def parse_pkglinkx_args() -> PkglinkxCliArgs:
    """Parse command-line arguments for pkglinkx."""
    parser = create_base_parser(
        prog_name='pkglinkx',
        description='pkglinkx: Make GitHub Python repos uvx-compatible for local CLI execution',
    )

    # Add pkglinkx-specific arguments
    parser.add_argument(
        '--skip-resources',
        action='store_true',
        help='Skip creating resource symlinks',
    )

    args = parser.parse_args()
    return PkglinkxCliArgs(
        source=args.source,
        directory=args.directory,
        symlink_name=args.symlink_name,
        skip_resources=args.skip_resources,
        verbose=resolve_verbosity(args),
        from_package=args.from_package,
        project_name=args.project_name,
        no_setup=args.no_setup,
        force=args.force,
        dry_run=args.dry_run,
    )
