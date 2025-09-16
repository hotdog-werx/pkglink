"""Tests for pkglink installation functionality."""

import hashlib
import subprocess
import tempfile
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pkglink import installation
from pkglink.installation import (
    _is_immutable_reference,
    _should_refresh_cache,
    find_package_root,
    install_with_uvx,
    resolve_source_path,
)
from pkglink.models import SourceSpec
from pkglink.parsing import build_uv_install_spec


class TestPackageRootFinding:
    """Tests for package root finding functions."""

    def test_find_package_root_exact_match(self) -> None:
        """Test finding package root with exact match."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            package_dir = temp_path / 'mypackage'
            package_dir.mkdir()
            (package_dir / 'resources').mkdir()

            result = find_package_root(temp_path, 'mypackage')
            assert result == package_dir

    def test_find_package_root_exact_match_no_target_subdir(self) -> None:
        """Test finding package root with exact match but no target subdir."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            package_dir = temp_path / 'mypackage'
            package_dir.mkdir()
            # No resources directory

            with pytest.raises(
                RuntimeError,
                match='Package "mypackage" not found',
            ):
                find_package_root(temp_path, 'mypackage')

    def test_find_package_root_platform_subdir_lib(self) -> None:
        """Test finding package root in platform subdirs (lib)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            lib_dir = temp_path / 'lib'
            lib_dir.mkdir()
            package_dir = lib_dir / 'mypackage'
            package_dir.mkdir()
            (package_dir / 'resources').mkdir()

            result = find_package_root(temp_path, 'mypackage')
            assert result == package_dir

    def test_find_package_root_platform_subdir_site_packages(self) -> None:
        """Test finding package root in platform subdirs (lib/site-packages)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            lib_dir = temp_path / 'Lib'
            lib_dir.mkdir()
            site_packages_dir = lib_dir / 'site-packages'
            site_packages_dir.mkdir()
            package_dir = site_packages_dir / 'mypackage'
            package_dir.mkdir()
            (package_dir / 'resources').mkdir()

            result = find_package_root(temp_path, 'mypackage')
            assert result == package_dir

    def test_find_package_root_not_found(self) -> None:
        """Test package root finding when package is not found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            # Create some other directories
            (temp_path / 'otherpackage').mkdir()

            with pytest.raises(
                RuntimeError,
                match='Package "mypackage" not found',
            ):
                find_package_root(temp_path, 'mypackage')

    def test_find_package_root_error_listing_directory(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test error handling when listing directory fails."""
        # Mock iterdir to raise an exception
        mock_path = mocker.Mock()
        mock_path.iterdir.side_effect = OSError('Permission denied')

        with pytest.raises(
            RuntimeError,
            match='Error accessing install directory',
        ):
            find_package_root(mock_path, 'anything')

    def test_find_package_root_avoids_fuzzy_match_bug(self) -> None:
        """Test that the refactored logic avoids the previous bug with fuzzy matching."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create multiple directories with resources (simulating the previous bug scenario)
            # toolbelt comes first alphabetically and has resources
            toolbelt_dir = temp_path / 'atoolbelt'
            toolbelt_dir.mkdir()
            (toolbelt_dir / 'resources').mkdir()
            (toolbelt_dir / 'resources' / 'toolbelt_file.txt').touch()

            # Target package comes later alphabetically and also has resources
            target_dir = temp_path / 'mypackage'
            target_dir.mkdir()
            (target_dir / 'resources').mkdir()
            (target_dir / 'resources' / 'target_file.txt').touch()

            # With the new logic, exact search should find 'mypackage'
            result = find_package_root(temp_path, 'mypackage')
            assert result == target_dir

            # And searching for non-existent package should fail cleanly
            with pytest.raises(
                RuntimeError,
                match='Package "nonexistent" not found',
            ):
                find_package_root(temp_path, 'nonexistent')

    def test_find_package_root_no_resources_in_platform_subdir(
        self,
        tmp_path: Path,
    ) -> None:
        """Test finding package root when package exists but no resources in platform subdir."""
        lib_dir = tmp_path / 'lib'
        lib_dir.mkdir()
        package_dir = lib_dir / 'mypackage'
        package_dir.mkdir()
        # No resources directory - this should fail

        with pytest.raises(
            RuntimeError,
            match='Package "mypackage" not found',
        ):
            find_package_root(tmp_path, 'mypackage')

    def test_find_package_root_no_site_packages_subdir(self) -> None:
        """Test platform subdir search when site-packages doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            lib_dir = temp_path / 'Lib'
            lib_dir.mkdir()
            # No site-packages directory, and no direct package match
            # This tests the early return in _search_in_site_packages

            with pytest.raises(
                RuntimeError,
                match='Package "mypackage" not found',
            ):
                find_package_root(temp_path, 'mypackage')

    def test_find_package_root_platform_subdirs_exist_but_no_package(
        self,
        tmp_path: Path,
    ) -> None:
        """Test when platform subdirs exist but don't contain the target package."""
        # Create platform subdirs but no target package in any of them
        lib_dir = tmp_path / 'lib'
        lib_dir.mkdir()
        (lib_dir / 'otherpackage').mkdir()

        lib64_dir = tmp_path / 'lib64'
        lib64_dir.mkdir()
        (lib64_dir / 'anotherpackage').mkdir()

        # This should hit the final return None in _search_in_platform_subdirs (line 108)
        with pytest.raises(
            RuntimeError,
            match='Package "mypackage" not found',
        ):
            find_package_root(tmp_path, 'mypackage')

    def test_find_package_root_package_in_site_packages_no_target_subdir(
        self,
        tmp_path: Path,
    ) -> None:
        """Test when package exists in site-packages but lacks target subdir."""
        # Create lib/site-packages structure
        lib_dir = tmp_path / 'lib'
        lib_dir.mkdir()
        site_packages_dir = lib_dir / 'site-packages'
        site_packages_dir.mkdir()

        # Create the package but without resources directory
        package_dir = site_packages_dir / 'mypackage'
        package_dir.mkdir()
        # No resources directory - this should hit the return None in _search_in_site_packages (line 108)

        with pytest.raises(
            RuntimeError,
            match='Package "mypackage" not found',
        ):
            find_package_root(tmp_path, 'mypackage')


class TestResolveSourcePath:
    """Tests for resolve_source_path function."""

    def test_resolve_local_source_exists(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test resolving local source path when it exists."""
        # Mock the uvx installation process for local sources
        fake_install_dir = tmp_path / 'cache' / 'pkglink_test'
        fake_install_dir.mkdir(parents=True, exist_ok=True)
        fake_package_root = fake_install_dir / 'test_package'
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

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            local_spec = SourceSpec(source_type='local', name=str(temp_path))

            result = resolve_source_path(local_spec)

        # Verify mocks were called
        mock_install_with_uvx.assert_called_once_with(local_spec)
        mock_find_package_root.assert_called_once_with(
            fake_install_dir,
            str(temp_path),
            'resources',
        )

        # Result should be the mocked package root
        assert result == fake_package_root

    def test_resolve_local_source_not_exists(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test resolving local source path when uvx installation fails."""
        # Mock uvx installation to fail for non-existent paths
        mocker.patch.object(
            installation,
            'install_with_uvx',
            side_effect=RuntimeError('Failed to install'),
        )

        nonexistent_path = '/nonexistent/path'
        local_spec = SourceSpec(source_type='local', name=nonexistent_path)

        with pytest.raises(RuntimeError, match='Failed to install'):
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
            'resources',
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
            'resources',
        )


class TestInstallWithUvx:
    """Tests for install_with_uvx function."""

    def test_install_with_uvx_cached(self, mocker: MockerFixture) -> None:
        """Test install_with_uvx when package is already cached and immutable."""
        with tempfile.TemporaryDirectory() as temp_home:
            temp_home_path = Path(temp_home)
            mocker.patch('pathlib.Path.home', return_value=temp_home_path)

            # Use an immutable reference (commit hash) so cache won't be refreshed
            spec = SourceSpec(
                source_type='github',
                name='repo',
                org='org',
                version='a' * 40,  # 40-char commit hash
            )

            # Calculate the actual cache directory name
            install_spec = build_uv_install_spec(spec)
            spec_hash = hashlib.sha256(install_spec.encode()).hexdigest()[:8]
            cache_dir = temp_home_path / '.cache' / 'pkglink' / f'{spec.name}_{spec_hash}'
            cache_dir.mkdir(parents=True)

            result = install_with_uvx(spec)

            # Should return the cached directory
            assert result == cache_dir

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

    def test_install_with_uvx_mutable_reference_refresh_cache(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test install_with_uvx when mutable reference needs cache refresh."""
        with tempfile.TemporaryDirectory() as temp_home:
            temp_home_path = Path(temp_home)
            mocker.patch('pathlib.Path.home', return_value=temp_home_path)

            # Create an existing cache directory for mutable reference
            spec = SourceSpec(
                source_type='github',
                name='repo',
                org='org',
                version='main',  # mutable branch reference
            )

            # Calculate cache directory and create it
            install_spec = build_uv_install_spec(spec)
            spec_hash = hashlib.sha256(install_spec.encode()).hexdigest()[:8]
            cache_dir = temp_home_path / '.cache' / 'pkglink' / f'{spec.name}_{spec_hash}'
            cache_dir.mkdir(parents=True)

            # Create a dummy file in cache to verify it gets removed
            dummy_file = cache_dir / 'dummy.txt'
            dummy_file.write_text('old cache')
            assert dummy_file.exists()

            # Mock subprocess.run to simulate successful uvx execution
            mock_run = mocker.patch('subprocess.run')
            mock_run.return_value = mocker.Mock(
                stdout=str(temp_home_path / 'site-packages') + '\n',
                stderr='',
            )

            # Mock shutil.copytree
            mocker.patch('shutil.copytree')

            result = install_with_uvx(spec)

            # Should have refreshed the cache (removed old directory)
            # The dummy file should no longer exist
            assert not dummy_file.exists()

            # Should have called subprocess.run with --force-reinstall
            mock_run.assert_called_once()
            cmd_args = mock_run.call_args[0][0]
            assert 'uvx' in cmd_args
            assert '--force-reinstall' in cmd_args

            # Should return the cache directory
            assert result == cache_dir

    def test_install_with_uvx_immutable_reference_no_force_reinstall(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test install_with_uvx for immutable reference without force reinstall."""
        with tempfile.TemporaryDirectory() as temp_home:
            temp_home_path = Path(temp_home)
            mocker.patch('pathlib.Path.home', return_value=temp_home_path)

            # Use immutable reference (package with version)
            spec = SourceSpec(
                source_type='package',
                name='requests',
                version='2.28.0',
            )

            # Mock subprocess.run to simulate successful uvx execution
            mock_run = mocker.patch('subprocess.run')
            mock_run.return_value = mocker.Mock(
                stdout=str(temp_home_path / 'site-packages') + '\n',
                stderr='',
            )

            # Mock shutil.copytree
            mocker.patch('shutil.copytree')

            result = install_with_uvx(spec)

            # Should have called subprocess.run without --force-reinstall
            mock_run.assert_called_once()
            cmd_args = mock_run.call_args[0][0]
            assert 'uvx' in cmd_args
            assert '--force-reinstall' not in cmd_args

            # Should return the cache directory
            assert str(result).startswith(
                str(temp_home_path / '.cache' / 'pkglink'),
            )


class TestMutableReferenceLogic:
    """Tests for mutable reference detection and caching logic."""

    def test_is_immutable_reference_package_with_version(self) -> None:
        """Test that packages with specific versions are immutable."""
        spec = SourceSpec(
            source_type='package',
            name='requests',
            version='2.28.0',
        )
        assert _is_immutable_reference(spec)  # Covers line 20

    def test_is_immutable_reference_package_without_version(self) -> None:
        """Test that packages without versions are mutable."""
        spec = SourceSpec(source_type='package', name='requests')
        assert not _is_immutable_reference(spec)

    def test_is_immutable_reference_github_commit_hash(self) -> None:
        """Test that GitHub commit hashes are immutable."""
        spec = SourceSpec(
            source_type='github',
            name='repo',
            org='org',
            version='a' * 40,  # 40-char hex commit hash
        )
        assert _is_immutable_reference(spec)  # Covers line 28

    def test_is_immutable_reference_github_version_tag(self) -> None:
        """Test that GitHub version tags are immutable."""
        test_cases = ['v1.2.3', '1.2.3', 'v10.20.30', '2.0.0-alpha.1']
        for version in test_cases:
            spec = SourceSpec(
                source_type='github',
                name='repo',
                org='org',
                version=version,
            )
            assert _is_immutable_reference(spec), f'Version {version} should be immutable'  # Covers line 37

    def test_is_immutable_reference_github_branch(self) -> None:
        """Test that GitHub branches are mutable."""
        test_cases = ['main', 'develop', 'feature-branch', 'fix/bug-123']
        for branch in test_cases:
            spec = SourceSpec(
                source_type='github',
                name='repo',
                org='org',
                version=branch,
            )
            assert not _is_immutable_reference(spec), f'Branch {branch} should be mutable'

    def test_is_immutable_reference_github_without_version(self) -> None:
        """Test that GitHub without version (default branch) is mutable."""
        spec = SourceSpec(source_type='github', name='repo', org='org')
        assert not _is_immutable_reference(spec)

    def test_should_refresh_cache_nonexistent_cache(self) -> None:
        """Test cache refresh when cache doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            nonexistent_cache = Path(temp_dir) / 'nonexistent'
            spec = SourceSpec(source_type='package', name='test')

            assert _should_refresh_cache(nonexistent_cache, spec)

    def test_should_refresh_cache_immutable_reference(self) -> None:
        """Test cache refresh for immutable references."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / 'cache'
            cache_dir.mkdir()

            # Immutable reference should not refresh cache
            spec = SourceSpec(
                source_type='package',
                name='requests',
                version='2.28.0',
            )
            assert not _should_refresh_cache(cache_dir, spec)

    def test_should_refresh_cache_mutable_reference(self) -> None:
        """Test cache refresh for mutable references."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / 'cache'
            cache_dir.mkdir()

            # Mutable reference should refresh cache
            spec = SourceSpec(
                source_type='github',
                name='repo',
                org='org',
                version='main',
            )
            assert _should_refresh_cache(cache_dir, spec)

    def test_install_with_uvx_force_reinstall_command_building(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test that force_reinstall flag is added to uvx command for mutable references."""
        with tempfile.TemporaryDirectory() as temp_home:
            temp_home_path = Path(temp_home)
            mocker.patch('pathlib.Path.home', return_value=temp_home_path)

            # Mock subprocess.run to capture the command
            mock_run = mocker.patch('subprocess.run')
            mock_run.return_value = mocker.Mock(
                stdout=str(temp_home_path / 'site-packages') + '\n',
                stderr='',
            )

            # Mock shutil.copytree
            mocker.patch('shutil.copytree')

            # Use mutable reference (branch)
            spec = SourceSpec(
                source_type='github',
                name='repo',
                org='org',
                version='main',
            )

            install_with_uvx(spec)

            # Verify the command includes --force-reinstall (covers line 318)
            mock_run.assert_called_once()
            cmd_args = mock_run.call_args[0][0]
            assert '--force-reinstall' in cmd_args
            assert 'uvx' in cmd_args

    def test_install_with_uvx_no_force_reinstall_for_immutable(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test that force_reinstall flag is NOT added for immutable references."""
        with tempfile.TemporaryDirectory() as temp_home:
            temp_home_path = Path(temp_home)
            mocker.patch('pathlib.Path.home', return_value=temp_home_path)

            # Mock subprocess.run to capture the command
            mock_run = mocker.patch('subprocess.run')
            mock_run.return_value = mocker.Mock(
                stdout=str(temp_home_path / 'site-packages') + '\n',
                stderr='',
            )

            # Mock shutil.copytree
            mocker.patch('shutil.copytree')

            # Use immutable reference (commit hash)
            spec = SourceSpec(
                source_type='github',
                name='repo',
                org='org',
                version='a' * 40,  # commit hash
            )

            install_with_uvx(spec)

            # Verify the command does NOT include --force-reinstall
            mock_run.assert_called_once()
            cmd_args = mock_run.call_args[0][0]
            assert '--force-reinstall' not in cmd_args
            assert 'uvx' in cmd_args
