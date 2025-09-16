"""Tests for pkglink setup functionality."""

from pathlib import Path

import pytest
import yaml

from pkglink.setup import (
    PostInstallConfig,
    SymlinkSpec,
    run_post_install_setup,
)


class TestSymlinkSpec:
    """Tests for SymlinkSpec model."""

    def test_symlink_spec_creation(self) -> None:
        """Test creating a SymlinkSpec."""
        spec = SymlinkSpec(
            source='configs/.editorconfig',
            target='.editorconfig',
        )
        assert spec.source == 'configs/.editorconfig'
        assert spec.target == '.editorconfig'


class TestPostInstallConfig:
    """Tests for PostInstallConfig model."""

    def test_empty_config(self) -> None:
        """Test creating an empty configuration."""
        config = PostInstallConfig()
        assert config.symlinks == []

    def test_config_with_symlinks(self) -> None:
        """Test creating configuration with symlinks."""
        spec = SymlinkSpec(
            source='configs/.editorconfig',
            target='.editorconfig',
        )
        config = PostInstallConfig(symlinks=[spec])
        assert len(config.symlinks) == 1
        assert config.symlinks[0].source == 'configs/.editorconfig'


class TestPostInstallSetup:
    """Tests for post-install setup functionality."""

    def test_no_config_file(self, tmp_path: Path) -> None:
        """Test when no pkglink.yaml exists."""
        linked_path = tmp_path / '.codeguide'
        linked_path.mkdir()

        # Should not raise an error
        run_post_install_setup(linked_path, tmp_path)

    def test_empty_config_file(self, tmp_path: Path) -> None:
        """Test with empty pkglink.yaml."""
        linked_path = tmp_path / '.codeguide'
        linked_path.mkdir()

        config_file = linked_path / 'pkglink.yaml'
        config_file.write_text('symlinks: []')

        # Should not raise an error
        run_post_install_setup(linked_path, tmp_path)

    def test_create_symlinks(self, tmp_path: Path) -> None:
        """Test creating symlinks from configuration."""
        linked_path = tmp_path / '.codeguide'
        linked_path.mkdir()

        # Create source files
        configs_dir = linked_path / 'configs'
        configs_dir.mkdir()
        editor_config = configs_dir / '.editorconfig'
        editor_config.write_text('root = true')

        # Create pkglink.yaml
        config_file = linked_path / 'pkglink.yaml'
        config_data = {
            'symlinks': [
                {'source': 'configs/.editorconfig', 'target': '.editorconfig'},
            ],
        }
        config_file.write_text(yaml.dump(config_data))

        # Run setup
        run_post_install_setup(linked_path, tmp_path)

        # Check that symlink was created
        target_file = tmp_path / '.editorconfig'
        assert target_file.exists()
        assert target_file.read_text() == 'root = true'

    def test_default_base_dir(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test using default base_dir (Path.cwd())."""
        linked_path = tmp_path / '.codeguide'
        linked_path.mkdir()

        # Create source files
        configs_dir = linked_path / 'configs'
        configs_dir.mkdir()
        editor_config = configs_dir / '.editorconfig'
        editor_config.write_text('root = true')

        # Create pkglink.yaml
        config_file = linked_path / 'pkglink.yaml'
        config_data = {
            'symlinks': [
                {'source': 'configs/.editorconfig', 'target': '.editorconfig'},
            ],
        }
        config_file.write_text(yaml.dump(config_data))

        # Change to tmp_path directory and run setup without base_dir
        monkeypatch.chdir(tmp_path)
        run_post_install_setup(linked_path)  # No base_dir parameter

        # Check that symlink was created in current directory
        target_file = tmp_path / '.editorconfig'
        assert target_file.exists()

    def test_yaml_load_error(self, tmp_path: Path) -> None:
        """Test error handling when YAML loading fails."""
        linked_path = tmp_path / '.codeguide'
        linked_path.mkdir()

        # Create invalid YAML file
        config_file = linked_path / 'pkglink.yaml'
        config_file.write_text('invalid: yaml: content: [')

        with pytest.raises(RuntimeError, match='Post-install setup failed'):
            run_post_install_setup(linked_path, tmp_path)
