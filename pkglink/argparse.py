import argparse
import re

from pkglink.models import ParsedSource
from pkglink.parsing import (
    extract_local_name,
    is_local_path,
    parse_github_source,
)


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
