import hashlib
import logging
import shutil
import subprocess
import tempfile
from difflib import SequenceMatcher
from pathlib import Path

from pkglink.models import SourceSpec
from pkglink.parsing import build_uv_install_spec

logger = logging.getLogger(__name__)


def find_python_package(install_dir: Path) -> Path | None:
    """Find the first directory with __init__.py (Python package)."""
    logger.debug(
        'Looking for Python package (with __init__.py) in %s',
        install_dir,
    )
    for item in install_dir.iterdir():
        if item.is_dir() and (item / '__init__.py').exists():
            logger.debug('Python package found: %s', item.name)
            return item
    logger.debug('No Python package found in %s', install_dir)
    return None


def find_with_resources(install_dir: Path) -> Path | None:
    """Find the first directory containing 'resources' folder."""
    logger.debug(
        'Looking for directory with resources folder in %s',
        install_dir,
    )
    for item in install_dir.iterdir():
        if item.is_dir() and (item / 'resources').exists():
            logger.debug('Directory with resources found: %s', item.name)
            return item
    logger.debug('No directory with resources found in %s', install_dir)
    return None


def find_exact_match(install_dir: Path, expected_name: str) -> Path | None:
    """Find a directory that exactly matches the expected name."""
    logger.debug(
        'Looking for exact match "%s" in %s',
        expected_name,
        install_dir,
    )
    target = install_dir / expected_name
    if target.is_dir():
        logger.debug('Exact match found: %s', target.name)
        return target
    logger.debug('No exact match found for "%s"', expected_name)
    return None


def find_by_prefix(install_dir: Path, expected_name: str) -> Path | None:
    """Find a directory that starts with the expected name."""
    logger.debug(
        'Looking for prefix match "%s*" in %s',
        expected_name,
        install_dir,
    )
    for item in install_dir.iterdir():
        if item.is_dir() and item.name.startswith(expected_name):
            logger.debug('Prefix match found: %s', item.name)
            return item
    logger.debug('No prefix match found for "%s"', expected_name)
    return None


def find_by_suffix(install_dir: Path, expected_name: str) -> Path | None:
    """Find a directory that ends with the expected name."""
    logger.debug(
        'Looking for suffix match "*%s" in %s',
        expected_name,
        install_dir,
    )
    for item in install_dir.iterdir():
        if item.is_dir() and item.name.endswith(expected_name):
            logger.debug('Suffix match found: %s', item.name)
            return item
    logger.debug('No suffix match found for "%s"', expected_name)
    return None


def find_by_similarity(install_dir: Path, expected_name: str) -> Path | None:
    """Find a directory with the highest similarity to the expected name."""
    logger.debug(
        'Looking for similarity match to "%s" in %s',
        expected_name,
        install_dir,
    )
    best_match = None
    best_ratio = 0.6  # Minimum similarity threshold

    for item in install_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.') and not item.name.endswith('.dist-info'):
            ratio = SequenceMatcher(
                None,
                expected_name.lower(),
                item.name.lower(),
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = item

    if best_match:
        logger.debug(
            'Similarity match found: %s (ratio: %.2f)',
            best_match.name,
            best_ratio,
        )
        return best_match

    logger.debug('No similarity match found for "%s"', expected_name)
    return None


def find_first_directory(install_dir: Path) -> Path | None:
    """Find the first non-hidden, non-dist-info directory."""
    logger.debug('Looking for first directory in %s', install_dir)
    for item in install_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.') and not item.name.endswith('.dist-info'):
            logger.debug('First directory found: %s', item.name)
            return item
    logger.debug('No suitable directory found in %s', install_dir)
    return None


def find_package_root(install_dir: Path, expected_name: str) -> Path:
    """Find the actual package directory after installation using multiple strategies."""
    logger.info('Looking for package root %s in %s', expected_name, install_dir)

    # List all items for debugging
    try:
        items = list(install_dir.iterdir())
        logger.info(
            'Available items in install directory: %s',
            [item.name for item in items],
        )
    except OSError as e:
        logger.exception('Error listing install directory')
        msg = f'Error accessing install directory {install_dir}: {e}'
        raise RuntimeError(msg) from e

    # Try multiple strategies
    strategies = [
        find_exact_match,
        find_python_package,
        find_with_resources,
        find_by_prefix,
        find_by_suffix,
        find_by_similarity,
        find_first_directory,
    ]

    for strategy in strategies:
        if strategy in [
            find_python_package,
            find_with_resources,
            find_first_directory,
        ]:
            result = strategy(install_dir)
        else:
            result = strategy(install_dir, expected_name)

        if result:
            logger.info(
                'Found package root using %s: %s',
                strategy.__name__,
                result,
            )
            return result

    # If all strategies fail, provide detailed error
    logger.error('Package root %s not found in %s', expected_name, install_dir)
    logger.error(
        'Available directories: %s',
        [
            item.name
            for item in items
            if item.is_dir() and not item.name.startswith('.') and not item.name.endswith('.dist-info')
        ],
    )
    msg = f'Package root {expected_name} not found in {install_dir}'
    raise RuntimeError(msg)


def resolve_source_path(
    spec: SourceSpec,
    module_name: str | None = None,
) -> Path:
    """Resolve source specification to an actual filesystem path."""
    logger.info(
        'Resolving source path for spec: %s, module: %s',
        spec,
        module_name,
    )

    if spec.source_type == 'local':
        # For local sources, return the path directly
        logger.info('Local source detected: %s', spec.name)
        path = Path(spec.name).resolve()
        if not path.exists():
            msg = f'Local path does not exist: {path}'
            raise RuntimeError(msg)
        logger.info('Resolved local path: %s', path)
        return path

    # For remote sources, try uvx first, then fallback to uv
    target_module = module_name or spec.name
    logger.info('Target module to find: %s', target_module)

    try:
        # Try uvx approach first
        logger.info('Attempting uvx installation')
        install_dir = install_with_uvx(spec)
    except Exception as e:
        logger.warning('uvx installation failed, trying fallback: %s', e)

        try:
            # Fallback to uv pip install --target
            logger.info('Attempting fallback uv installation')
            install_dir = install_with_uv(spec)
        except Exception as fallback_error:
            logger.exception('Both uvx and uv installation methods failed')
            msg = f'Failed to install {spec}: uvx error: {e}, uv error: {fallback_error}'
            raise RuntimeError(msg) from fallback_error
        else:
            package_root = find_package_root(install_dir, target_module)
            logger.info(
                'Successfully resolved via uv fallback: %s',
                package_root,
            )
            return package_root
    else:
        package_root = find_package_root(install_dir, target_module)
        logger.info('Successfully resolved via uvx: %s', package_root)
        return package_root


def install_with_uvx(spec: SourceSpec) -> Path:
    """Install package using uvx, then copy to a predictable location."""
    logger.info('Installing %s using uvx', spec.name)

    install_spec = build_uv_install_spec(spec)
    logger.debug('Install spec: %s', install_spec)

    # Create a predictable cache directory that we control
    cache_base = Path.home() / '.cache' / 'pkglink'
    cache_base.mkdir(parents=True, exist_ok=True)

    # Use a hash of the install spec to create a unique cache directory
    # Remove the inline import
    spec_hash = hashlib.sha256(install_spec.encode()).hexdigest()[:8]
    cache_dir = cache_base / f'{spec.name}_{spec_hash}'

    # If already cached, return the existing directory
    if cache_dir.exists():
        logger.info('Using cached installation: %s', cache_dir)
        return cache_dir

    try:
        # Use uvx to install, then use uvx to run a script that tells us the site-packages
        cmd = [
            'uvx',
            '--from',
            install_spec,
            'python',
            '-c',
            'import site; print(site.getsitepackages()[0])',
        ]
        logger.debug('Running uvx command: %s', ' '.join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        # Get the site-packages directory from uvx's environment
        site_packages = Path(result.stdout.strip())
        logger.info('uvx installed to site-packages: %s', site_packages)

        # Copy the site-packages to our cache directory
        shutil.copytree(site_packages, cache_dir)
        logger.info('Cached uvx installation to: %s', cache_dir)

    except subprocess.CalledProcessError as e:
        logger.exception('uvx installation failed')
        msg = f'Failed to install {spec.name} with uvx: {e.stderr}'
        raise RuntimeError(msg) from e
    else:
        return cache_dir


def install_with_uv(spec: SourceSpec) -> Path:
    """Install package using uv pip install --target."""
    logger.info('Installing %s using uv fallback approach', spec.name)

    # Use a temporary directory for installation
    temp_dir = Path(tempfile.mkdtemp(prefix='pkglink_uv_'))

    try:
        install_spec = build_uv_install_spec(spec)
        logger.debug('Install spec: %s', install_spec)

        cmd = ['uv', 'pip', 'install', '--target', str(temp_dir), install_spec]
        logger.debug('Running command: %s', ' '.join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        logger.debug('Installation successful, output: %s', result.stdout)
    except subprocess.CalledProcessError as e:
        logger.exception('uv installation failed')
        shutil.rmtree(temp_dir, ignore_errors=True)
        msg = f'Failed to install {spec.name} with uv: {e.stderr}'
        raise RuntimeError(msg) from e
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    else:
        return temp_dir
