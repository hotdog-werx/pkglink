"""Tests for pkglink installation functionality."""

import hashlib
import tempfile
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pkglink import installation
from pkglink.installation import (
    _should_refresh_cache,
    find_package_root,
    install_with_uvx,
)
from pkglink.models import GitHubSourceSpec, PackageSourceSpec
from pkglink.parsing import build_uv_install_spec

DUMMY_TOKEN = 'not-a-real-token'  # noqa: S105


class TestMutableReferenceLogic:
    """Tests for mutable reference detection and caching logic."""

    def test_is_immutable_reference_package_with_version(self) -> None:
        """Test that packages with specific versions are immutable."""
        spec = PackageSourceSpec(
            name='requests',
            version='==2.28.0',
            project_name='requests',
        )
        assert spec.is_immutable_reference()  # Covers line 20

    def test_is_mutable_reference_package_with_version_range(self) -> None:
        """Test that packages with specific versions are immutable."""
        spec = PackageSourceSpec(
            name='requests',
            version='>=2,<3',
            project_name='requests',
        )
        assert not spec.is_immutable_reference()

    def test_is_immutable_reference_package_without_version(self) -> None:
        """Test that packages without versions are mutable."""
        spec = PackageSourceSpec(
            name='requests',
            project_name='requests',
        )
        assert not spec.is_immutable_reference()

    def test_is_immutable_reference_github_commit_hash(self) -> None:
        """Test that GitHub commit hashes are immutable."""
        spec = GitHubSourceSpec(
            name='repo',
            org='org',
            version='a' * 40,  # 40-char hex commit hash
            project_name='repo',
        )
        assert spec.is_immutable_reference()  # Covers line 28

    def test_is_immutable_reference_github_version_tag(self) -> None:
        """Test that GitHub version tags are immutable."""
        test_cases = ['v1.2.3', '1.2.3', 'v10.20.30']
        for version in test_cases:
            spec = GitHubSourceSpec(
                name='repo',
                org='org',
                version=version,
                project_name='repo',
            )
            assert spec.is_immutable_reference(), f'Version {version} should be immutable'  # Covers line 37

    def test_is_immutable_reference_github_branch(self) -> None:
        """Test that GitHub branches are mutable."""
        test_cases = ['main', 'develop', 'feature-branch']
        for branch in test_cases:
            spec = GitHubSourceSpec(
                name='repo',
                org='org',
                version=branch,
                project_name='repo',
            )
            assert not spec.is_immutable_reference(), f'Branch {branch} should be mutable'

    def test_is_immutable_reference_github_without_version(self) -> None:
        """Test that GitHub without version (default branch) is mutable."""
        spec = GitHubSourceSpec(
            name='repo',
            org='org',
            project_name='repo',
        )
        assert not spec.is_immutable_reference()

    def test_should_refresh_cache_nonexistent_cache(self) -> None:
        """Test cache refresh when cache doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            nonexistent_cache = Path(temp_dir) / 'nonexistent'
            spec = PackageSourceSpec(
                name='test',
                project_name='test',
            )

            assert _should_refresh_cache(nonexistent_cache, spec)

    def test_should_refresh_cache_immutable_reference(self) -> None:
        """Test cache refresh for immutable references."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / 'cache'
            cache_dir.mkdir()

            # Immutable reference should not refresh cache
            spec = PackageSourceSpec(
                name='requests',
                version='==2.28.0',
                project_name='requests',
            )
            assert not _should_refresh_cache(cache_dir, spec)

    def test_should_refresh_cache_mutable_reference(self) -> None:
        """Test cache refresh for mutable references."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / 'cache'
            cache_dir.mkdir()

            # Mutable reference should refresh cache
            spec = GitHubSourceSpec(
                name='repo',
                org='org',
                version='main',
                project_name='repo',
            )
            assert _should_refresh_cache(cache_dir, spec)


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

    def test_find_package_root_not_found(self) -> None:
        """Test package root finding when package is not found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            # Create some other directories
            (temp_path / 'otherpackage').mkdir()

            with pytest.raises(
                RuntimeError,
                match="Package 'mypackage' not found in",
            ):
                find_package_root(temp_path, 'mypackage')


class TestInstallWithUvx:
    """Minimal tests for install_with_uvx function."""

    def test_install_with_uvx_cached(self, mocker: MockerFixture) -> None:
        """Test install_with_uvx returns cached directory and dist-info name."""
        with tempfile.TemporaryDirectory() as temp_home:
            temp_home_path = Path(temp_home)
            mocker.patch('pathlib.Path.home', return_value=temp_home_path)
            spec = GitHubSourceSpec(
                name='repo',
                org='org',
                version='a' * 40,
                project_name='repo',
            )
            install_spec = build_uv_install_spec(spec)
            spec_hash = hashlib.sha256(install_spec.encode()).hexdigest()[:8]
            cache_dir = temp_home_path / '.cache' / 'pkglink' / f'{spec.name}_{spec_hash}'
            cache_dir.mkdir(parents=True)
            (cache_dir / '.pkglink_dist_info').write_text(
                'repo-1.0.0.dist-info',
            )
            result = install_with_uvx(spec)
            assert result == (cache_dir, 'repo-1.0.0.dist-info', None)

    def test_install_with_uvx_command_failure(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test install_with_uvx when uvx command fails."""
        with tempfile.TemporaryDirectory() as temp_home:
            temp_home_path = Path(temp_home)
            mocker.patch('pathlib.Path.home', return_value=temp_home_path)
            mock_get_site_packages = mocker.patch.object(
                installation,
                'get_site_packages_path',
            )
            mock_get_site_packages.side_effect = RuntimeError('uvx failed')
            mocker.patch.object(Path, 'exists', return_value=False)
            spec = GitHubSourceSpec(
                name='repo',
                org='org',
                project_name='repo',
            )
            with pytest.raises(RuntimeError, match='Failed to install'):
                install_with_uvx(spec)

    def test_install_with_uvx_expands_index_url_env_vars(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv('PKG_TOKEN', DUMMY_TOKEN)
        mocker.patch('pathlib.Path.home', return_value=tmp_path)
        captured: dict[str, str | None] = {}

        def _fake_install(
            spec: PackageSourceSpec,
            install_spec: str,
            cache_dir: Path,
            *,
            index_url: str | None = None,
        ) -> tuple[Path, str, Path | None]:
            captured['index_url'] = index_url
            return cache_dir, 'demo.dist-info', None

        mocker.patch.object(
            installation,
            '_perform_uvx_installation',
            side_effect=_fake_install,
        )

        spec = PackageSourceSpec(
            name='private-package',
            project_name='private-package',
        )
        install_with_uvx(
            spec,
            index_url='https://${PKG_TOKEN}@packages.example.com/simple',
        )

        assert captured['index_url'] == f'https://{DUMMY_TOKEN}@packages.example.com/simple'
