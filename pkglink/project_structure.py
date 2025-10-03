import tomli_w
from hotlog import get_logger

from pkglink.models import PackageInfo

logger = get_logger(__name__)


def generate_pyproject_toml(
    package_name: str,
    python_module_name: str,
    package_info: PackageInfo,
) -> str:
    """Generate a pyproject.toml file for uvx compatibility.

    Args:
        package_name: The package name for the project (from metadata)
        python_module_name: The Python module name (for packages config)
        package_info: Package information including version, console scripts, and dependencies
        install_spec: Source specification for the package

    Returns:
        Contents of the pyproject.toml file as a string
    """
    # Use package name from metadata if available, otherwise fall back to package_name
    project_name = package_info.metadata.get('name', package_name)

    # Create base project configuration
    project_config = {
        'name': project_name,
        'version': package_info.version,
        'description': package_info.metadata.get(
            'summary',
            f'{project_name} package',
        ),
        'dependencies': [],
        'requires-python': package_info.metadata.get(
            'requires_python',
            '>=3.8',
        ),
    }

    # Add dependencies if available
    if package_info.dependencies:
        project_config['dependencies'] = list(package_info.dependencies)

    # Create pyproject structure
    pyproject_data = {
        'build-system': {
            'requires': ['hatchling'],
            'build-backend': 'hatchling.build',
        },
        'project': project_config,
    }

    # Add console scripts if available
    if package_info.console_scripts:
        pyproject_data['project']['scripts'] = package_info.console_scripts

    # Add packages configuration if module name differs from package name
    if python_module_name != project_name:
        pyproject_data['tool'] = {
            'hatch': {
                'build': {
                    'targets': {
                        'wheel': {'packages': [f'src/{python_module_name}']},
                    },
                },
            },
        }

    # Use tomli_w to convert to TOML string
    toml_content = tomli_w.dumps(pyproject_data)

    logger.debug(
        'generated_pyproject_toml',
        project_name=project_name,
        python_module_name=python_module_name,
        version=package_info.version,
        has_console_scripts=bool(package_info.console_scripts),
        has_dependencies=bool(package_info.dependencies),
        dependency_count=len(package_info.dependencies) if package_info.dependencies else 0,
    )

    return toml_content
