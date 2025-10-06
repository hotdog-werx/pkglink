# pkglink

Create symlinks to python package directories from PyPI packages or GitHub repos
into your current working directory.

This package provides a unified CLI with three complementary subcommands:

- **`pkglink link`**: Access resources from any Python package or GitHub repo
- **`pkglink tool`**: Make GitHub Python projects `uvx`-compatible for CLI
  execution inside `.pkglink/`
- **`pkglink sync`**: Read project configuration from `pkglink.config.yaml` and
  process multiple pkglink operations in staged batches

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

### pkglink link

`pkglink` is a CLI tool designed for configuration sharing and quick access to
package resources. It allows you to symlink specific directories (like
`resources`, `configs`, `templates`) from Python packages directly into your
current directory without having to install them globally or manually download
files.

### pkglink tool

`pkglink tool` is designed specifically for GitHub Python repositories. It
creates a `.pkglink` directory structure that makes any GitHub Python project
compatible with `uvx` for CLI tool execution, even if the project wasn't
originally designed for it.

### pkglink sync

`pkglink sync` lets you define multiple resources and CLI packages inside a
`pkglink.config.yaml` file and execute them in three deterministic phases:
download, plan, and execute. The batch process downloads every package up front
(failing fast if any fetch errors occur), generates execution plans for each
entry, and finally runs all filesystem operations and post-install setup. This
keeps logs grouped by phase and ensures a partially completed batch never writes
to disk.

## Installation

### Using uvx (Recommended)

Once published, you can use both tools directly with `uvx` without installation:

```bash
# Use pkglink link for resource linking
uvx pkglink link --from tbelt toolbelt resources

# Use pkglink tool for GitHub repo CLI access
uvx pkglink tool github:org/awesome-cli-tool

# Then run the CLI tool
uvx --from .pkglink/awesome-cli-tool some-command
```

### Local Installation

For development or repeated use:

```bash
pip install pkglink
```

## Usage

### pkglink link - Resource Linking

#### Basic Examples

```bash
# Symlink the 'resources' directory from 'mypackage'
pkglink link mypackage resources

# Use --from to install one package but link from another module
pkglink link --from tbelt toolbelt resources

# Specify a custom symlink name
pkglink link --symlink-name .configs mypackage configs

# Create symlinks inside .pkglink directory (unified with pkglink tool)
pkglink link --inside-pkglink --from tbelt toolbelt resources

# Dry run to see what would happen
pkglink link --dry-run mypackage templates

# Force overwrite existing symlinks
pkglink link --force mypackage resources
```

#### Command Line Options

- `source`: The package to install (can be PyPI package or GitHub repo)
- `directory`: The subdirectory within the package to symlink (default:
  "resources")
- `--from PACKAGE`: Install one package but look for the module in another
- `--symlink-name NAME`: Custom name for the symlink (default: `.{source}`)
- `--inside-pkglink`: Create symlink inside `.pkglink` directory instead of
  current directory
- `--force`: Overwrite existing symlinks/directories
- `--dry-run`: Show what would be done without making changes
- `--verbose`: Enable verbose logging
- `--no-setup`: Skip running post-install setup (pkglink.yaml)

### pkglink tool - GitHub CLI Tools

#### Basic Examples

```bash
# Make a GitHub repo uvx-compatible (basic usage)
pkglink tool github:org/awesome-cli-tool

# Then run CLI commands
uvx --from .pkglink/awesome-cli-tool some-command

# With specific version
pkglink tool github:org/tool@v1.2.0

# Skip resource linking (CLI tools only)
pkglink tool --skip-resources github:org/pure-cli-tool

# Custom resource directory and symlink name
pkglink tool -d configs -s .my-configs github:org/config-tool
```

#### Command Line Options

- `source`: GitHub repository specification (github:org/repo[@version])
- `-d, --directory`: Target subdirectory to link (default: "resources")
- `-s, --symlink-name`: Name for the resource symlink (default: `.{repo-name}`)
- `--skip-resources`: Skip creating resource symlinks
- `--verbose`: Enable verbose logging

#### Generated Structure

`pkglink tool` creates a structured `.pkglink` directory:

```
.pkglink/
├── awesome-cli-tool/          # Package directory
│   ├── pyproject.toml         # Generated project file
│   ├── src/                   # Source code symlink
│   │   └── awesome_cli_tool/  # → symlinked to cached package
│   └── .pkglink-metadata.yaml # Metadata for version tracking
└── .awesome-cli-tool          # Resource symlink (if resources exist)
```

**Note**: If the target symlink already exists, `pkglink` will skip the
operation and exit successfully (unless `--force` is used). This makes it safe
to run in setup scripts multiple times.

### pkglink sync - YAML Automation

`pkglink sync` reads link definitions from `pkglink.config.yaml` and executes
each one in three stages. Each link uses the same flags available on
`pkglink link` or `pkglink tool`, so you can mix resource links and `.pkglink`
uvx setups in one run.

#### Example `pkglink.config.yaml`

```yaml
defaults:
  inside_pkglink: true
  directory: resources

links:
  codeguide:
    source: github:hotdog-werx/codeguide@topic/updates
    project_name: codeguide
    symlink_name: .codeguide

  toolbelt-cli:
    source: github:hotdog-werx/toolbelt@v0.0.1
    from: tbelt
    project_name: tbelt
    inside_pkglink: false
    skip_resources: true
```

> **Warning:** Each link must resolve to a unique `project_name` and
> `symlink_name`. If two entries collide, `pkglink sync` will exit before
> downloading anything and list the duplicates so you can fix them safely.

Run the batch:

```bash
pkglink sync  # reads pkglink.config.yaml in the current directory
```

The CLI will:

1. Download every package (stop immediately if any download fails)
2. Generate execution plans using the cached downloads
3. Apply each plan and run `pkglink.yaml` post-install setup where applicable

Use `pkglink sync --dry-run` to preview all plans without touching the
filesystem. You can override the configuration path with
`pkglink sync --config path/to/pkglink.config.yaml`.

## ⚠️ Important Notes & Gotchas

### GitHub Repository Naming

When using GitHub repositories, `pkglink` automatically converts repository
names from **kebab-case** (hyphens) to **snake_case** (underscores) to match
Python module naming conventions.

```bash
# Repository: github:org/my-awesome-package
# Python module: my_awesome_package

# This works automatically:
pkglink link github:org/my-awesome-package resources
# pkglink automatically looks for module 'my_awesome_package'

# If the auto-conversion doesn't match, use --from:
pkglink link --from github:org/repo-with-hyphens actual_module_name
```

**Why this matters:**

- GitHub repositories often use kebab-case: `my-package-name`
- Python modules must use snake_case: `my_package_name`
- Without conversion, `pkglink` would look for the wrong module name

**Examples:**

- `github:org/data-science-toolkit` → looks for module `data_science_toolkit`
- `github:org/ml-models` → looks for module `ml_models`
- `github:org/project-templates` → looks for module `project_templates`

## Advanced Usage

```bash
# GitHub repositories
pkglink user/repo configs

# Specific versions
pkglink link mypackage==1.2.0 resources

# With custom names and force overwrite
pkglink link --symlink-name .my-configs --force mypackage configs

# Skip post-install setup
pkglink link --no-setup mypackage resources
```

## Post-Install Setup

`pkglink` supports automatic post-install setup through `pkglink.yaml`
configuration files. After creating the main symlink, `pkglink` will look for a
`pkglink.yaml` file in the linked directory and automatically create additional
symlinks as specified.

### Configuration Format

Create a `pkglink.yaml` file in your package's `resources` directory:

```yaml
symlinks:
  - source: configs/.editorconfig
    target: .editorconfig
  - source: configs/.gitignore
    target: .gitignore
  - source: configs/pyproject.toml
    target: pyproject.toml
```

### Example Usage

For a package like `codeguide` with this structure:

```
codeguide/
└── resources/
    ├── pkglink.yaml
    └── configs/
        ├── .editorconfig
        ├── .gitignore
        └── pyproject.toml
```

Running `pkglink link codeguide` will:

1. Create `.codeguide/` symlink to the resources directory
2. Read `.codeguide/pkglink.yaml`
3. Automatically create additional symlinks:
   - `.editorconfig` → `.codeguide/configs/.editorconfig`
   - `.gitignore` → `.codeguide/configs/.gitignore`
   - `pyproject.toml` → `.codeguide/configs/pyproject.toml`

### Options

- **Automatic**: Post-install setup runs automatically when `pkglink.yaml`
  exists
- **Skip**: Use `--no-setup` flag to disable post-install setup
- **Safe**: Invalid configurations are logged but don't stop the main linking
  process

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

### Configuration Sharing (pkglink)

```bash
# Share configuration templates across projects
pkglink link --symlink-name .eslintrc my-configs eslint
pkglink link --symlink-name .github my-configs github-workflows

# Unified organization with pkglink tool
pkglink link --inside-pkglink --from tbelt toolbelt resources
```

### Resource Access (pkglink)

```bash
# Access package resources for development
pkglink link --from data-science-toolkit datasets data
pkglink link ml-models pretrained
```

### Template Management (pkglink)

```bash
# Quick access to project templates
pkglink link project-templates react
pkglink link --symlink-name .templates cookiecutter-templates django
```

### CLI Tool Access (pkglink tool)

```bash
# Make any GitHub Python project usable as a CLI tool
pkglink tool github:microsoft/pylint-extensions
uvx --from .pkglink/pylint-extensions pylint --load-plugins=...

# Development tools
pkglink tool github:psf/black
uvx --from .pkglink/black black --version

# Custom CLI tools
pkglink tool github:myorg/internal-tool
uvx --from .pkglink/internal-tool tool-command --help
```

### Unified Workflow

Both tools can work together for complete project setup:

```bash
# Set up CLI tools
pkglink tool github:org/awesome-linter
pkglink tool --skip-resources github:org/code-formatter

# Set up shared resources  
pkglink link --inside-pkglink --from tbelt toolbelt resources
pkglink link --inside-pkglink my-configs eslint

# Now everything is organized under .pkglink/
ls .pkglink/
# awesome-linter/  code-formatter/  .tbelt/  .my-configs/

# Use the tools
uvx --from .pkglink/awesome-linter lint-code
uvx --from .pkglink/code-formatter format-code
```

## Benefits

### pkglink link

- **Fast**: Leverages `uvx` caching + additional persistent caching
- **Reliable**: Uses `uv`'s robust package installation with multiple fallback
  strategies
- **Flexible**: Supports PyPI packages, GitHub repos, and local paths
- **Safe**: Dry-run mode and intelligent conflict detection
- **Organized**: Optional `--inside-pkglink` for unified structure with pkglink
  tool
- **Convenient**: Can be used with `uvx` without installation
- **Authenticated**: Inherits all `uv` authentication for private repositories

### pkglink tool

- **Universal**: Makes any GitHub Python project uvx-compatible
- **Automatic**: Generates proper `pyproject.toml` from package metadata
- **Cross-platform**: Uses robust symlink creation with Windows fallback
- **Version-aware**: Tracks and refreshes mutable references (branches)
- **Resource-friendly**: Optional resource directory linking
- **CLI-focused**: Optimized for command-line tool usage
- **Standards-compliant**: Creates proper Python package structure

### Combined

- **Unified Organization**: Both tools can create symlinks in `.pkglink/`
  directory
- **Comprehensive**: Covers both resource access and CLI tool execution
- **Consistent**: Shared authentication, caching, and safety features
- **Scalable**: Supports everything from single configs to complex multi-tool
  setups

## Requirements

- **`uv`** (required) - Handles all package installation and authentication
- Python 3.11+
- `uvx` (part of `uv`, used for package installation)
