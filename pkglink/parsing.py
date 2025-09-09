"""Source parsing utilities for pkglink."""

import re
from pathlib import Path

from pkglink.models import SourceSpec


def parse_source(source: str) -> SourceSpec:
    """Parse a source string into a SourceSpec.

    Supports formats:
    - github:org/repo[@version]
    - package-name[@version]
    - ./local/path or /absolute/path
    """
    # GitHub format: github:org/repo[@version]
    github_match = re.match(r'^github:([^/]+)/([^@]+)(?:@(.+))?$', source)
    if github_match:
        org, repo, version = github_match.groups()
        return SourceSpec(
            source_type='github',
            name=repo,
            org=org,
            version=version,
        )

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
