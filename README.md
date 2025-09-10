# pkglink

Create symlinks to python package directories from PyPI packages or GitHub repos
into your current working directory.

## ⚠️ Requirements

**This tool requires `uv` to be installed on your system.**

`pkglink` depends entirely on the [`uv`](https://docs.astral.sh/uv/) package
manager for all installation and authentication tasks. `uv` handles:

- Package installation from PyPI
- GitHub repository handling
- Authentication for private repositories
- Dependency resolution and caching
- Environment isolation via `uvx`

**Install `uv` first:**

```bash
# Install uv (see https://docs.astral.sh/uv/getting-started/installation/)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

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

**Note**: If the target symlink already exists, `pkglink` will skip the
operation and exit successfully (unless `--force` is used). This makes it safe
to run in setup scripts multiple times.

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

`pkglink` leverages `uv`'s powerful package management capabilities through its
`uvx` tool:

### 1. uvx Integration

- **Package Installation**: Uses `uvx` (part of `uv`) to install packages in
  isolated environments
- **Dependency Resolution**: Leverages `uv`'s robust dependency handling and
  authentication
- **Environment Isolation**: Each package gets proper isolation via `uvx`
- **Authentication**: Inherits all `uv` authentication for private repositories

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

- **Fast**: Leverages `uvx` caching + additional persistent caching
- **Reliable**: Uses `uv`'s robust package installation with multiple fallback
  strategies for package discovery
- **Flexible**: Supports PyPI packages, GitHub repos, and local paths
- **Safe**: Dry-run mode and intelligent conflict detection
- **Convenient**: Can be used with `uvx` without installation
- **Authenticated**: Inherits all `uv` authentication for private repositories

## Requirements

- **`uv`** (required) - Handles all package installation and authentication
- Python 3.11+
- `uvx` (part of `uv`, used for package installation)
