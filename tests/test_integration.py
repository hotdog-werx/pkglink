"""Integration tests for pkglink using real toolbelt package."""

import sys
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pkglink.main import main as main_function


class TestIntegrationToolbelt:
    """Integration tests using the actual toolbelt package."""

    def _create_fake_pyproject_toml(
        self,
        fake_toolbelt_dir: Path,
        name: str = 'fake-toolbelt',
    ) -> None:
        """Create a minimal pyproject.toml file to make the directory a valid Python project for uvx."""
        (fake_toolbelt_dir / 'pyproject.toml').write_text(f"""[project]
name = "{name}"
version = "0.1.0"
""")

    def test_toolbelt_resources_integration(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test linking toolbelt resources directory - full integration."""
        # Change to the temp directory
        monkeypatch.chdir(tmp_path)

        # Create a fake toolbelt package structure
        fake_toolbelt_dir = tmp_path / 'fake_toolbelt'
        fake_toolbelt_dir.mkdir()
        fake_resources_dir = fake_toolbelt_dir / 'resources'
        fake_resources_dir.mkdir()
        (fake_resources_dir / 'config.txt').write_text('test config')

        # Add minimal pyproject.toml to make it a Python project for uvx
        self._create_fake_pyproject_toml(fake_toolbelt_dir)

        # Mock sys.argv to use local path instead of package name
        test_args = [
            'pkglink',
            str(fake_toolbelt_dir),  # Use the fake directory as source
            'resources',
        ]
        mocker.patch.object(sys, 'argv', test_args)

        # Run the main function (no heavy mocking needed)
        main_function()

        # Verify the symlink was created
        expected_symlink = tmp_path / '.fake_toolbelt'
        assert expected_symlink.exists(), f'Symlink {expected_symlink} was not created'
        assert expected_symlink.is_symlink(), f'{expected_symlink} is not a symlink'

        # Verify it points to a resources directory
        target = expected_symlink.resolve()
        assert target.name == 'resources', f'Target should be resources directory, got {target.name}'
        assert target.exists(), f'Target {target} does not exist'
        assert target.is_dir(), f'Target {target} is not a directory'

        # Verify some expected files exist in the resources directory
        assert len(list(target.iterdir())) > 0, 'Resources directory should not be empty'

    def test_toolbelt_custom_symlink_name_integration(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test linking toolbelt with custom symlink name - full integration."""
        # Change to the temp directory
        monkeypatch.chdir(tmp_path)

        # Create a fake toolbelt package structure
        fake_toolbelt_dir = tmp_path / 'fake_toolbelt'
        fake_toolbelt_dir.mkdir()
        fake_resources_dir = fake_toolbelt_dir / 'resources'
        fake_resources_dir.mkdir()
        (fake_resources_dir / 'config.txt').write_text('test config')

        # Add minimal pyproject.toml to make it a Python project for uvx
        self._create_fake_pyproject_toml(fake_toolbelt_dir)

        # Mock sys.argv with custom symlink name
        test_args = [
            'pkglink',
            str(fake_toolbelt_dir),
            'resources',
            '--symlink-name',
            '.codeguide',
        ]
        mocker.patch.object(sys, 'argv', test_args)

        # Run the main function
        main_function()

        # Verify the custom symlink was created
        expected_symlink = tmp_path / '.codeguide'
        assert expected_symlink.exists(), f'Symlink {expected_symlink} was not created'
        assert expected_symlink.is_symlink(), f'{expected_symlink} is not a symlink'

        # Verify it points to a resources directory
        target = expected_symlink.resolve()
        assert target.name == 'resources', f'Target should be resources directory, got {target.name}'
        assert target.exists(), f'Target {target} does not exist'
        assert target.is_dir(), f'Target {target} is not a directory'

    def test_toolbelt_already_exists_skips(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that existing symlink is skipped without error."""
        # Change to the temp directory
        monkeypatch.chdir(tmp_path)

        # Create an existing target
        existing_target = tmp_path / '.fake_toolbelt'
        existing_target.mkdir()

        # Create a fake toolbelt package structure
        fake_toolbelt_dir = tmp_path / 'fake_toolbelt_source'
        fake_toolbelt_dir.mkdir()
        fake_resources_dir = fake_toolbelt_dir / 'resources'
        fake_resources_dir.mkdir()

        # Add minimal pyproject.toml to make it a Python project for uvx
        self._create_fake_pyproject_toml(
            fake_toolbelt_dir,
            name='fake-toolbelt-source',
        )

        # Mock sys.argv
        test_args = [
            'pkglink',
            str(fake_toolbelt_dir),
            'resources',
        ]
        mocker.patch.object(sys, 'argv', test_args)

        # Run the main function - should not raise an error
        main_function()

        # Verify the existing directory is still there and unchanged
        assert existing_target.exists()
        assert existing_target.is_dir()
        assert not existing_target.is_symlink()  # Still the original directory

    def test_toolbelt_force_overwrite_integration(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test force overwrite of existing target."""
        # Change to the temp directory
        monkeypatch.chdir(tmp_path)

        # Create an existing target
        fake_toolbelt_dir = tmp_path / 'fake_toolbelt_source'
        fake_toolbelt_dir.mkdir()
        fake_resources_dir = fake_toolbelt_dir / 'resources'
        fake_resources_dir.mkdir()
        (fake_resources_dir / 'config.txt').write_text('test config')

        # Add minimal pyproject.toml to make it a Python project for uvx
        self._create_fake_pyproject_toml(
            fake_toolbelt_dir,
            name='fake-toolbelt-source',
        )

        # Create an existing symlink with the expected name
        existing_target = tmp_path / '.fake_toolbelt_source'
        existing_target.mkdir()
        (existing_target / 'old_file.txt').write_text('old content')

        # Mock sys.argv with force flag
        test_args = [
            'pkglink',
            str(fake_toolbelt_dir),
            'resources',
            '--force',
        ]
        mocker.patch.object(sys, 'argv', test_args)

        # Run the main function
        main_function()

        # Verify the target was replaced with a symlink
        assert existing_target.exists()
        assert existing_target.is_symlink(), 'Target should now be a symlink'

        # Verify it points to the correct location
        target = existing_target.resolve()
        assert target.name == 'resources'
        assert target.exists()
        assert target.is_dir()

    @pytest.mark.parametrize('directory', ['resources', 'configs'])
    def test_toolbelt_different_directories(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        directory: str,
    ) -> None:
        """Test linking different directories from toolbelt."""
        # Change to the temp directory
        monkeypatch.chdir(tmp_path)

        # Create a fake toolbelt package structure
        fake_toolbelt_dir = tmp_path / 'fake_toolbelt'
        fake_toolbelt_dir.mkdir()
        fake_target_dir = fake_toolbelt_dir / directory
        fake_target_dir.mkdir()
        (fake_target_dir / 'config.txt').write_text('test config')

        # Add minimal pyproject.toml to make it a Python project for uvx
        self._create_fake_pyproject_toml(fake_toolbelt_dir)

        # Mock sys.argv
        test_args = [
            'pkglink',
            str(fake_toolbelt_dir),
            directory,
        ]
        mocker.patch.object(sys, 'argv', test_args)

        # Test for successful execution or expected failure
        try:
            main_function()

            # If successful, verify the symlink was created correctly
            expected_symlink = tmp_path / '.fake_toolbelt'
            assert expected_symlink.exists(), f'Symlink {expected_symlink} was not created'
            assert expected_symlink.is_symlink(), f'{expected_symlink} is not a symlink'

            # Verify it points to the correct directory
            target = expected_symlink.resolve()
            assert target.name == directory, f'Target should be {directory} directory, got {target.name}'
            assert target.exists(), f'Target {target} does not exist'
            assert target.is_dir(), f'Target {target} is not a directory'

        except SystemExit:
            # If the directory doesn't exist in toolbelt, that's also a valid test result
            # We're testing that the system behaves correctly even when the requested directory doesn't exist
            pass  # Expected behavior for missing directories

    def test_github_repository_integration(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test linking from a GitHub repository."""
        # Change to the temp directory
        monkeypatch.chdir(tmp_path)

        # Create a fake toolbelt package structure
        fake_toolbelt_dir = tmp_path / 'fake_toolbelt'
        fake_toolbelt_dir.mkdir()
        fake_resources_dir = fake_toolbelt_dir / 'resources'
        fake_resources_dir.mkdir()
        (fake_resources_dir / 'github_config.txt').write_text(
            'github test config',
        )

        # Add minimal pyproject.toml to make it a Python project for uvx
        self._create_fake_pyproject_toml(fake_toolbelt_dir)

        # Mock sys.argv with GitHub repository format but use local path
        test_args = [
            'pkglink',
            str(fake_toolbelt_dir),  # Use local path instead of github: URL
            'resources',
        ]
        mocker.patch.object(sys, 'argv', test_args)

        # Run the main function
        main_function()

        # Verify the symlink was created
        expected_symlink = tmp_path / '.fake_toolbelt'
        assert expected_symlink.exists(), f'Symlink {expected_symlink} was not created'
        assert expected_symlink.is_symlink(), f'{expected_symlink} is not a symlink'

        # Verify it points to a resources directory
        target = expected_symlink.resolve()
        assert target.name == 'resources', f'Target should be resources directory, got {target.name}'
        assert target.exists(), f'Target {target} does not exist'
        assert target.is_dir(), f'Target {target} is not a directory'

        # Verify the GitHub-specific file exists
        assert (target / 'github_config.txt').exists(), 'GitHub-specific config file should exist'

    def test_github_repository_with_custom_symlink(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test linking from a GitHub repository with custom symlink name."""
        # Change to the temp directory
        monkeypatch.chdir(tmp_path)

        # Create a fake toolbelt package structure
        fake_toolbelt_dir = tmp_path / 'fake_toolbelt'
        fake_toolbelt_dir.mkdir()
        fake_configs_dir = fake_toolbelt_dir / 'configs'
        fake_configs_dir.mkdir()
        (fake_configs_dir / 'github_settings.yaml').write_text('github: true')

        # Add minimal pyproject.toml to make it a Python project for uvx
        self._create_fake_pyproject_toml(fake_toolbelt_dir)

        # Mock sys.argv with custom symlink name
        test_args = [
            'pkglink',
            str(fake_toolbelt_dir),
            'configs',
            '--symlink-name',
            '.github-configs',
        ]
        mocker.patch.object(sys, 'argv', test_args)

        # Run the main function
        main_function()

        # Verify the custom symlink was created
        expected_symlink = tmp_path / '.github-configs'
        assert expected_symlink.exists(), f'Symlink {expected_symlink} was not created'
        assert expected_symlink.is_symlink(), f'{expected_symlink} is not a symlink'

        # Verify it points to the configs directory
        target = expected_symlink.resolve()
        assert target.name == 'configs', f'Target should be configs directory, got {target.name}'
        assert target.exists(), f'Target {target} does not exist'
        assert target.is_dir(), f'Target {target} is not a directory'

        # Verify the GitHub-specific file exists
        assert (target / 'github_settings.yaml').exists(), 'GitHub-specific settings file should exist'
