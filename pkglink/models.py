from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints


class SourceSpec(BaseModel):
    """Represents a parsed source specification."""

    source_type: Literal['github', 'package', 'local']
    name: Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
    version: str | None = None
    org: str | None = None  # For GitHub sources
    local_path: str | None = None  # For local sources, stores the original path


class LinkTarget(BaseModel):
    """Represents the target for a symlink operation."""

    model_config = ConfigDict(
        # Serialize Path objects as strings
        json_encoders={Path: str},
    )

    source_path: Path
    target_directory: Annotated[
        str,
        StringConstraints(min_length=1, strip_whitespace=True),
    ] = 'resources'
    symlink_name: str | None = None

    @property
    def resolved_source_path(self) -> Path:
        """Get the resolved absolute path."""
        return self.source_path.resolve()


class LinkOperation(BaseModel):
    """Represents a complete link operation."""

    model_config = ConfigDict(
        # Serialize Path objects as strings
        json_encoders={Path: str},
    )

    spec: SourceSpec
    target: LinkTarget
    force: bool = False
    dry_run: bool = False

    @property
    def symlink_name(self) -> str:
        """Get the final symlink name."""
        symlink_name = self.target.symlink_name
        return symlink_name if symlink_name else f'.{self.spec.name}'

    @property
    def full_source_path(self) -> Path:
        """Get the full path to the source directory."""
        return self.target.resolved_source_path / self.target.target_directory


class CliArgs(BaseModel):
    """Command line arguments model."""

    source: str
    directory: str = 'resources'
    symlink_name: str | None = None
    force: bool = False
    dry_run: bool = False
    verbose: bool = False
    from_package: str | None = None
