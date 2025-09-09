"""Example demonstrating pkglink usage."""

import tempfile
from pathlib import Path

from pkglink.parsing import parse_source
from pkglink.symlinks import create_symlink


def demo_basic_usage() -> None:
    """Demonstrate basic pkglink functionality."""
    print('pkglink Demo')
    print('=' * 50)

    # Example 1: Parse GitHub source
    print('\n1. Parsing GitHub source:')
    github_spec = parse_source('github:myorg/config-repo@v1.0.0')
    print(f'   Type: {github_spec.source_type}')
    print(f'   Org: {github_spec.org}')
    print(f'   Name: {github_spec.name}')
    print(f'   Version: {github_spec.version}')

    # Example 2: Parse package source
    print('\n2. Parsing package source:')
    package_spec = parse_source('my-config-package@2.1.0')
    print(f'   Type: {package_spec.source_type}')
    print(f'   Name: {package_spec.name}')
    print(f'   Version: {package_spec.version}')

    # Example 3: Parse local source
    print('\n3. Parsing local source:')
    local_spec = parse_source('./local-configs')
    print(f'   Type: {local_spec.source_type}')
    print(f'   Name: {local_spec.name}')

    # Example 4: Demonstrate symlink creation (with temp directories)
    print('\n4. Demonstrating symlink creation:')
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a source directory with resources
        source_dir = temp_path / 'config-source'
        resources_dir = source_dir / 'resources'
        resources_dir.mkdir(parents=True)

        # Create some example config files
        (resources_dir / 'pyproject.toml').write_text(
            '[tool.ruff]\nline-length = 88\n',
        )
        (resources_dir / '.gitignore').write_text('__pycache__/\n*.pyc\n')

        # Create a target location
        target_dir = temp_path / 'project'
        target_dir.mkdir()

        # Change to target directory and create symlink
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(target_dir)

            # Create symlink
            symlink_path = target_dir / '.config'
            is_symlink = create_symlink(resources_dir, symlink_path)

            if is_symlink:
                print(
                    f'   ✓ Created symlink: {symlink_path.name} -> {resources_dir}',
                )
            else:
                print(
                    f'   ✓ Created copy: {symlink_path.name} (symlinks not supported)',
                )

            # List contents
            print(f'   Contents: {list(symlink_path.iterdir())}')

        finally:
            os.chdir(original_cwd)


if __name__ == '__main__':
    demo_basic_usage()
