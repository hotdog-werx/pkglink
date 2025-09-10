# pkglink

Create symlinks to python package directories from PyPI packages or GitHub repos
into your current working directory.

## Overview

`pkglink` is a CLI tool designed for configuration sharing and quick access to
package resources. It allows you to symlink specific directories (like
`resources`, `configs`, `templates`) from Python packages directly into your
current directory without having to install them globally or manually download
files.

## Installation

### Using uvx (Recommended)

Once published, you can use `pkglink` directly with `uvx` without installation:

```bash
# Use a specific subdirectory from a package
uvx pkglink --from tbelt toolbelt resources

# Symlink with a custom name
uvx pkglink --symlink-name .codeguide tbelt resources
```

### Local Installation

For development or repeated use:

```bash
pip install pkglink
```

## Usage

### Basic Examples

```bash
# Symlink the 'resources' directory from 'mypackage'
pkglink mypackage resources

# Use --from to install one package but link from another module
pkglink --from tbelt toolbelt resources

# Specify a custom symlink name
pkglink --symlink-name .configs mypackage configs

# Dry run to see what would happen
pkglink --dry-run mypackage templates

# Force overwrite existing symlinks
pkglink --force mypackage resources
```

### Command Line Options

- `source`: The package to install (can be PyPI package or GitHub repo)
- `directory`: The subdirectory within the package to symlink (default:
  "resources")
- `--from PACKAGE`: Install one package but look for the module in another
  (useful when the PyPI package name differs from the Python module name)
- `--symlink-name NAME`: Custom name for the symlink (default: `.{source}`)
- `--force`: Overwrite existing symlinks/directories
- `--dry-run`: Show what would be done without making changes
- `--verbose`: Enable verbose logging

### Advanced Usage

```bash
# GitHub repositories
pkglink user/repo configs

# Specific versions
pkglink mypackage==1.2.0 resources

# With custom names and force overwrite
pkglink --symlink-name .my-configs --force mypackage configs
```

## How It Works

`pkglink` leverages a hybrid approach combining `uvx`'s efficient package
management with its own intelligent caching system:

### 1. uvx Integration

- **First Installation**: Uses `uvx` to install packages in isolated
  environments
- **Dependency Resolution**: Leverages `uvx`'s robust dependency handling
- **Environment Isolation**: Each package gets proper isolation via `uvx`

### 2. Intelligent Caching

- **Location**: `~/.cache/pkglink/{package}_{hash}/`
- **Persistence**: Survives `uvx` cleanup operations
- **Performance**: Subsequent runs are near-instantaneous
- **Hash-based**: Each unique package specification gets its own cache directory

### 3. Package Discovery

`pkglink` uses multiple strategies to find the correct package directory after
installation:

1. **Exact Match**: Direct directory name matching
2. **Python Package Detection**: Looks for directories with `__init__.py`
3. **Resource Directory Detection**: Finds directories containing a `resources`
   folder
4. **Prefix/Suffix Matching**: Flexible name matching
5. **Similarity Matching**: Fuzzy matching for close names
6. **Fallback**: Uses the first suitable directory

### 4. Fallback Mechanism

If `uvx` installation fails, `pkglink` automatically falls back to direct
`uv pip install --target` installation, ensuring reliability across different
environments.

## Use Cases

### Configuration Sharing

```bash
# Share configuration templates across projects
pkglink --symlink-name .eslintrc my-configs eslint
pkglink --symlink-name .github my-configs github-workflows
```

### Resource Access

```bash
# Access package resources for development
pkglink --from data-science-toolkit datasets data
pkglink ml-models pretrained
```

### Template Management

```bash
# Quick access to project templates
pkglink project-templates react
pkglink --symlink-name .templates cookiecutter-templates django
```

## Benefits

- **Fast**: Leverages uvx caching + additional persistent caching
- **Reliable**: Multiple fallback strategies for package discovery
- **Flexible**: Supports PyPI packages, GitHub repos, and local paths
- **Safe**: Dry-run mode and intelligent conflict detection
- **Convenient**: Can be used with uvx without installation

## Requirements

- Python 3.11+
- `uv` (automatically used for package installation)
- `uvx` (optional, for running without installation)
