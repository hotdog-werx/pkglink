"""Pydantic models for pkglink."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator


class SourceSpec(BaseModel):
    """Represents a parsed source specification."""

    source_type: Literal['github', 'package', 'local']
    name: str
    version: str | None = None
    org: str | None = None  # For GitHub sources

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate that name is not empty."""
        if not v.strip():
            msg = 'Source name cannot be empty'
            raise ValueError(msg)
        return v.strip()


class LinkTarget(BaseModel):
    """Represents the target for a symlink operation."""

    source_path: Path
    target_directory: str = 'resources'
    symlink_name: str | None = None

    @field_validator('source_path')
    @classmethod
    def validate_source_path(cls, v: Path) -> Path:
        """Resolve source path to absolute path."""
        return v.resolve()

    @field_validator('target_directory')
    @classmethod
    def validate_target_directory(cls, v: str) -> str:
        """Validate that target directory is not empty."""
        if not v.strip():
            msg = 'Target directory cannot be empty'
            raise ValueError(msg)
        return v.strip()


class LinkOperation(BaseModel):
    """Represents a complete link operation."""

    spec: SourceSpec
    target: LinkTarget
    force: bool = False
    dry_run: bool = False

    @property
    def symlink_name(self) -> str:
        """Get the final symlink name."""
        if self.target.symlink_name:
            return self.target.symlink_name
        return f'.{self.spec.name}'

    @property
    def full_source_path(self) -> Path:
        """Get the full path to the source directory."""
        return self.target.source_path / self.target.target_directory
