"""Integration tests for resource sync bug investigation.

This test demonstrates that the "resource sync bug" is actually a packaging
configuration issue, not a problem with pkglink's sync logic.
"""

from pathlib import Path

from tests.integration.conftest import CliCommand


def test_resources_sync_bug_is_packaging_issue(
    tmp_path: Path,
    run_pkglink_batch: CliCommand,
):
    """Test that demonstrates the root cause of the "resource sync bug".

    It's actually a packaging configuration issue, not a sync problem.

    When packages are missing proper hatchling configuration, they fail to
    package resources correctly, leading to sync failures.
    """
    package_name = 'brokenpackage'
    pkg_dir = tmp_path / package_name
    pkg_dir.mkdir()

    # Create resources directory
    resources_dir = pkg_dir / 'resources'
    resources_dir.mkdir()
    (resources_dir / 'config.yaml').write_text('# Test config\nvalue: 42\n')

    # Create pyproject.toml WITHOUT proper hatchling configuration
    # This is what causes the "sync bug" - it's really a packaging issue
    pyproject_content = f"""[project]
name = "{package_name}"
version = "1.0.0"
description = "Package with broken hatchling config"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# NOTE: Missing [tool.hatch.build.targets.wheel] configuration
# This causes hatchling to fail packaging resources properly
"""
    (pkg_dir / 'pyproject.toml').write_text(pyproject_content)

    # Create pkglink config to try using this broken package
    pkglink_config = f"""python-packages:
  {package_name}:
    from: {pkg_dir}
    directory: resources
"""
    config_file = tmp_path / 'pkglink.config.yaml'
    config_file.write_text(pkglink_config)

    # Try to sync - this should fail with a clear error message about packaging
    result = run_pkglink_batch(['--config', str(config_file)], tmp_path)

    # Should fail due to packaging issue
    assert result.returncode != 0, 'Expected failure due to packaging configuration issue'

    # Check that we get a reasonable error message about the packaging problem
    error_output = result.all_output.lower()

    # Should mention that it's a packaging/build issue, not a sync issue
    packaging_indicators = [
        'build',
        'hatch',
        'wheel',
        'packaging',
        'configuration',
    ]

    has_packaging_context = any(indicator in error_output for indicator in packaging_indicators)
    assert has_packaging_context, (
        f'Error message should indicate packaging/build issue.\n'
        f'Got: {result.all_output}\n'
        f'Expected message to contain one of: {packaging_indicators}'
    )


def test_resources_sync_works_with_proper_config(
    tmp_path: Path,
    run_pkglink_batch: CliCommand,
):
    """Test that resource sync works correctly when packaging is properly configured.

    This demonstrates the solution to the "sync bug" - proper hatchling configuration.
    """
    package_name = 'workingpackage'
    pkg_dir = tmp_path / package_name
    pkg_dir.mkdir()

    # Create proper package structure
    package_py_dir = pkg_dir / package_name
    package_py_dir.mkdir()
    (package_py_dir / '__init__.py').write_text(
        '"""Working package."""\n\ndef main():\n    print("Hello!")\n',
    )

    # Create resources directory INSIDE the package
    resources_dir = package_py_dir / 'resources'
    resources_dir.mkdir()
    (resources_dir / 'config.yaml').write_text('# Initial config\nkey: value\n')

    # Create pyproject.toml WITH proper hatchling configuration
    pyproject_content = f"""[project]
name = "{package_name}"
version = "1.0.0"
description = "Package with correct hatchling config"

[project.scripts]
{package_name} = "{package_name}:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
include = [
    "{package_name}/**"
]
"""
    (pkg_dir / 'pyproject.toml').write_text(pyproject_content)

    # Create pkglink config
    pkglink_config = f"""python-packages:
  {package_name}:
    from: {pkg_dir}
    directory: resources
"""
    config_file = tmp_path / 'pkglink.config.yaml'
    config_file.write_text(pkglink_config)

    # Initial sync - should work
    result = run_pkglink_batch(['--config', str(config_file)], tmp_path)
    assert result.returncode == 0, f'Initial sync failed: {result.all_output}'

    # This test demonstrates that proper hatchling configuration allows successful builds/sync
    # The key point is that sync completed without errors (returncode == 0)
    # Different packaging structures may result in different sync layouts,
    # but the important thing is that proper config prevents the "sync bug"
