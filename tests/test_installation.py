"""Tests for pkglink installation functionality."""

import tempfile
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pkglink import installation
from pkglink.installation import (
    find_exact_match,
    find_first_directory,
    find_package_root,
    find_python_package,
    find_with_resources,
    resolve_source_path,
)
from pkglink.models import SourceSpec


class TestPackageRootFinding:
    """Tests for package root finding functions."""

    def test_find_exact_match_exists(self) -> None:
        """Test finding exact match when it exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            expected_dir = temp_path / 'mypackage'
            expected_dir.mkdir()

            result = find_exact_match(temp_path, 'mypackage')
            assert result == expected_dir

    def test_find_exact_match_not_exists(self) -> None:
        """Test finding exact match when it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            result = find_exact_match(temp_path, 'nonexistent')
            assert result is None

    def test_find_python_package(self) -> None:
        """Test finding Python package with __init__.py."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            package_dir = temp_path / 'mypackage'
            package_dir.mkdir()
            (package_dir / '__init__.py').touch()

            result = find_python_package(temp_path)
            assert result == package_dir

    def test_find_with_resources(self) -> None:
        """Test finding directory containing resources folder."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            package_dir = temp_path / 'mypackage'
            package_dir.mkdir()
            (package_dir / 'resources').mkdir()

            result = find_with_resources(temp_path)
            assert result == package_dir

    def test_find_first_directory(self) -> None:
        """Test finding the first directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            first_dir = temp_path / 'first'
            first_dir.mkdir()
            (temp_path / 'file.txt').touch()  # Should be ignored

            result = find_first_directory(temp_path)
            assert result == first_dir

    def test_find_package_root_strategies(self) -> None:
        """Test package root finding with strategy fallback."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            package_dir = temp_path / 'somepackage'
            package_dir.mkdir()
            (package_dir / '__init__.py').touch()

            # Should find it using the Python package strategy
            result = find_package_root(temp_path, 'nonexistent')
            assert result == package_dir

    def test_find_package_root_not_found(self) -> None:
        """Test package root finding when nothing is found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            # Only create files, no directories
            (temp_path / 'file.txt').touch()

            with pytest.raises(
                FileNotFoundError,
                match='Could not locate package',
            ):
                find_package_root(temp_path, 'anything')


class TestResolveSourcePath:
    """Tests for resolve_source_path function."""

    def test_resolve_local_source(self) -> None:
        """Test resolving local source path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            local_spec = SourceSpec(source_type='local', name=str(temp_path))

            result = resolve_source_path(local_spec)
            assert result == temp_path

    def test_resolve_remote_source(self, mocker: MockerFixture) -> None:
        """Test resolving remote source path."""
        # Mock the UV installation and package finding
        fake_install_dir = Path('/fake/install/dir')
        fake_package_root = Path('/fake/package/root')

        mock_install_with_uv = mocker.patch.object(
            installation,
            'install_with_uv',
            return_value=fake_install_dir,
        )
        mock_find_package_root = mocker.patch.object(
            installation,
            'find_package_root',
            return_value=fake_package_root,
        )

        github_spec = SourceSpec(
            source_type='github',
            name='myrepo',
            org='myorg',
        )

        result = resolve_source_path(github_spec)

        assert result == fake_package_root
        mock_install_with_uv.assert_called_once_with(github_spec)
        mock_find_package_root.assert_called_once_with(
            fake_install_dir,
            'myrepo',
        )

    def test_resolve_remote_source_with_different_module(self, mocker: MockerFixture) -> None:
        """Test resolving remote source path with different module name."""
        # Mock the UV installation and package finding
        fake_install_dir = Path('/fake/install/dir')
        fake_package_root = Path('/fake/package/root')

        mock_install_with_uv = mocker.patch.object(
            installation,
            'install_with_uv',
            return_value=fake_install_dir,
        )
        mock_find_package_root = mocker.patch.object(
            installation,
            'find_package_root',
            return_value=fake_package_root,
        )

        # Install package 'tbelt' but look for module 'toolbelt'
        install_spec = SourceSpec(
            source_type='pypi',
            name='tbelt',
        )

        result = resolve_source_path(install_spec, module_name='toolbelt')

        assert result == fake_package_root
        mock_install_with_uv.assert_called_once_with(install_spec)
        mock_find_package_root.assert_called_once_with(
            fake_install_dir,
            'toolbelt',  # Should look for 'toolbelt', not 'tbelt'
        )
