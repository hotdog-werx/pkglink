"""Tests for pkglink installation functionality."""

import subprocess
import tempfile
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pkglink import installation
from pkglink.installation import (
    find_by_prefix,
    find_by_similarity,
    find_by_suffix,
    find_exact_match,
    find_first_directory,
    find_package_root,
    find_python_package,
    find_with_resources,
    install_with_uvx,
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

    def test_find_by_prefix_exists(self) -> None:
        """Test finding directory by prefix."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            package_dir = temp_path / 'mypackage-main'
            package_dir.mkdir()

            result = find_by_prefix(temp_path, 'mypackage')
            assert result == package_dir

    def test_find_by_prefix_not_exists(self) -> None:
        """Test finding directory by prefix when none match."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / 'otherpackage').mkdir()

            result = find_by_prefix(temp_path, 'mypackage')
            assert result is None

    def test_find_by_suffix_exists(self) -> None:
        """Test finding directory by suffix."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            package_dir = temp_path / 'main-mypackage'
            package_dir.mkdir()

            result = find_by_suffix(temp_path, 'mypackage')
            assert result == package_dir

    def test_find_by_suffix_not_exists(self) -> None:
        """Test finding directory by suffix when none match."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / 'otherpackage').mkdir()

            result = find_by_suffix(temp_path, 'mypackage')
            assert result is None

    def test_find_by_similarity_high_match(self) -> None:
        """Test finding directory by similarity with high match."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            package_dir = temp_path / 'my-package'
            package_dir.mkdir()

            result = find_by_similarity(temp_path, 'mypackage')
            assert result == package_dir

    def test_find_by_similarity_low_match(self) -> None:
        """Test finding directory by similarity with low match."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / 'completely-different').mkdir()

            result = find_by_similarity(temp_path, 'mypackage')
            assert result is None

    def test_find_by_similarity_below_threshold(self) -> None:
        """Test finding directory by similarity below threshold."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            # Create a directory with very low similarity
            (temp_path / 'xyz').mkdir()

            result = find_by_similarity(temp_path, 'mypackage')
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
                RuntimeError,
                match='Package root anything not found in',
            ):
                find_package_root(temp_path, 'anything')

    def test_find_package_root_error_listing_directory(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test error handling when listing directory fails."""
        # Mock iterdir to raise an exception
        mock_path = mocker.Mock()
        mock_path.iterdir.side_effect = OSError('Permission denied')
        mock_path.exists.return_value = True

        mocker.patch('pathlib.Path', return_value=mock_path)

        with pytest.raises(
            RuntimeError,
            match='Error accessing install directory',
        ):
            find_package_root(mock_path, 'anything')


class TestResolveSourcePath:
    """Tests for resolve_source_path function."""

    def test_resolve_local_source_exists(self) -> None:
        """Test resolving local source path when it exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            local_spec = SourceSpec(source_type='local', name=str(temp_path))

            result = resolve_source_path(local_spec)
            assert result == temp_path

    def test_resolve_local_source_not_exists(self) -> None:
        """Test resolving local source path when it doesn't exist."""
        nonexistent_path = '/nonexistent/path'
        local_spec = SourceSpec(source_type='local', name=nonexistent_path)

        with pytest.raises(RuntimeError, match='Local path does not exist'):
            resolve_source_path(local_spec)

    def test_resolve_remote_source(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test resolving remote source path."""
        # Mock the uvx installation and package finding
        fake_install_dir = tmp_path / 'mock' / 'install' / 'dir'
        fake_install_dir.mkdir(parents=True, exist_ok=True)
        fake_package_root = tmp_path / 'mock' / 'package' / 'root'
        fake_package_root.mkdir(parents=True, exist_ok=True)

        mock_install_with_uvx = mocker.patch.object(
            installation,
            'install_with_uvx',
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
        mock_install_with_uvx.assert_called_once_with(github_spec)
        mock_find_package_root.assert_called_once_with(
            fake_install_dir,
            'myrepo',
        )

    def test_resolve_remote_source_with_different_module(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test resolving remote source path with different module name."""
        # Mock the uvx installation and package finding
        fake_install_dir = tmp_path / 'mock' / 'install' / 'dir'
        fake_install_dir.mkdir(parents=True, exist_ok=True)
        fake_package_root = tmp_path / 'mock' / 'package' / 'root'
        fake_package_root.mkdir(parents=True, exist_ok=True)

        mock_install_with_uvx = mocker.patch.object(
            installation,
            'install_with_uvx',
            return_value=fake_install_dir,
        )
        mock_find_package_root = mocker.patch.object(
            installation,
            'find_package_root',
            return_value=fake_package_root,
        )

        # Install package 'tbelt' but look for module 'toolbelt'
        install_spec = SourceSpec(
            source_type='package',
            name='tbelt',
        )

        result = resolve_source_path(install_spec, module_name='toolbelt')

        assert result == fake_package_root
        mock_install_with_uvx.assert_called_once_with(install_spec)
        mock_find_package_root.assert_called_once_with(
            fake_install_dir,
            'toolbelt',  # Should look for 'toolbelt', not 'tbelt'
        )


class TestInstallWithUvx:
    """Tests for install_with_uvx function."""

    def test_install_with_uvx_cached(self, mocker: MockerFixture) -> None:
        """Test install_with_uvx when package is already cached."""
        with tempfile.TemporaryDirectory() as temp_home:
            temp_home_path = Path(temp_home)
            mocker.patch('pathlib.Path.home', return_value=temp_home_path)
            mocker.patch.object(Path, 'exists', return_value=True)

            spec = SourceSpec(source_type='github', name='repo', org='org')

            result = install_with_uvx(spec)

            # Should return the cached directory
            assert str(result).startswith(
                str(temp_home_path / '.cache' / 'pkglink'),
            )

    def test_install_with_uvx_not_cached(self, mocker: MockerFixture) -> None:
        """Test install_with_uvx when package is not cached."""
        with tempfile.TemporaryDirectory() as temp_home:
            temp_home_path = Path(temp_home)
            # Mock subprocess.run to simulate successful uvx execution
            mock_run = mocker.patch('subprocess.run')
            mock_run.return_value = mocker.Mock(
                stdout=str(temp_home_path / 'site-packages') + '\n',
                stderr='',
            )

            # Mock the cache directory to not exist initially
            mocker.patch.object(Path, 'exists', return_value=False)
            mocker.patch('pathlib.Path.home', return_value=temp_home_path)

            # Mock shutil.copytree
            mocker.patch('shutil.copytree')

            spec = SourceSpec(source_type='github', name='repo', org='org')

            result = install_with_uvx(spec)

            # Should have called subprocess.run
            mock_run.assert_called_once()
            assert 'uvx' in str(mock_run.call_args[0][0])

            # Should return the cache directory
            assert str(result).startswith(
                str(temp_home_path / '.cache' / 'pkglink'),
            )

    def test_install_with_uvx_command_failure(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test install_with_uvx when uvx command fails."""
        with tempfile.TemporaryDirectory() as temp_home:
            temp_home_path = Path(temp_home)
            mocker.patch('pathlib.Path.home', return_value=temp_home_path)

            # Mock subprocess.run to raise CalledProcessError
            mock_run = mocker.patch('subprocess.run')
            mock_run.side_effect = subprocess.CalledProcessError(
                1,
                'uvx',
                stderr='uvx failed',
            )

            mocker.patch.object(Path, 'exists', return_value=False)

            spec = SourceSpec(source_type='github', name='repo', org='org')

            with pytest.raises(RuntimeError, match='Failed to install'):
                install_with_uvx(spec)
