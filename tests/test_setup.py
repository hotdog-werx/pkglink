"""Tests for pkglink setup functionality."""

from pathlib import Path

import yaml

from pkglink.setup import (
    run_post_install_setup,
)


class TestPostInstallSetup:
    """Tests for post-install setup functionality."""

    def test_no_config_file(self, tmp_path: Path) -> None:
        """Test when no pkglink.yaml exists."""
        linked_path = tmp_path / '.codeguide'
        linked_path.mkdir()

        # Should not raise an error
        created = run_post_install_setup(linked_path, tmp_path)
        assert created == []

    def test_empty_config_file(self, tmp_path: Path) -> None:
        """Test with empty pkglink.yaml."""
        linked_path = tmp_path / '.codeguide'
        linked_path.mkdir()

        config_file = linked_path / 'pkglink.yaml'
        config_file.write_text('symlinks: []')

        # Should not raise an error
        created = run_post_install_setup(linked_path, tmp_path)
        assert created == []

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
        created = run_post_install_setup(linked_path, tmp_path)

        # Check that symlink was created
        target_file = tmp_path / '.editorconfig'
        assert target_file.exists()
        assert target_file.read_text() == 'root = true'
        assert created == [
            {'source': 'configs/.editorconfig', 'target': '.editorconfig'},
        ]
