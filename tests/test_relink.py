"""Tests for symlink re-linking behavior and target checking."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pkglink.main import (
    _is_symlink_pointing_to_correct_target,
    check_target_exists,
    resolve_and_create_operation_with_source,
)
from pkglink.models import CliArgs, LinkOperation, SourceSpec


class TestCheckTargetExists:
    """Tests for the updated check_target_exists function."""

    def test_target_does_not_exist(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test when target symlink does not exist."""
        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
            symlink_name='.mypackage',
        )
        spec = SourceSpec(source_type='package', name='mypackage')
        source_path = tmp_path / 'source'

        # Change working directory using monkeypatch
        monkeypatch.chdir(tmp_path)
        result = check_target_exists(args, spec, source_path)
        assert result is False

    def test_target_exists_and_correct(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test when target exists and points to correct location."""
        # Create source structure
        source_path = tmp_path / 'source'
        source_path.mkdir()
        (source_path / 'resources').mkdir()

        # Create symlink pointing to correct location
        symlink_path = tmp_path / '.mypackage'
        symlink_path.symlink_to(
            source_path / 'resources',
            target_is_directory=True,
        )

        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
            symlink_name='.mypackage',
        )
        spec = SourceSpec(source_type='package', name='mypackage')

        # Change working directory using monkeypatch
        monkeypatch.chdir(tmp_path)
        result = check_target_exists(args, spec, source_path)
        assert result is True

    def test_target_exists_but_wrong_location(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test when target exists but points to wrong location."""
        # Create two source structures
        old_source = tmp_path / 'old_source'
        old_source.mkdir()
        (old_source / 'resources').mkdir()

        new_source = tmp_path / 'new_source'
        new_source.mkdir()
        (new_source / 'resources').mkdir()

        # Create symlink pointing to old location
        symlink_path = tmp_path / '.mypackage'
        symlink_path.symlink_to(
            old_source / 'resources',
            target_is_directory=True,
        )

        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
            symlink_name='.mypackage',
        )
        spec = SourceSpec(source_type='package', name='mypackage')

        # Change working directory using monkeypatch
        monkeypatch.chdir(tmp_path)
        # Check with new source (should not skip since symlink points to old)
        result = check_target_exists(args, spec, new_source)
        assert result is False

    def test_target_exists_but_not_symlink(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test when target exists but is not a symlink."""
        # Create source structure
        source_path = tmp_path / 'source'
        source_path.mkdir()
        (source_path / 'resources').mkdir()

        # Create directory (not symlink) at target location
        target_path = tmp_path / '.mypackage'
        target_path.mkdir()

        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
            symlink_name='.mypackage',
        )
        spec = SourceSpec(source_type='package', name='mypackage')

        # Change working directory using monkeypatch
        monkeypatch.chdir(tmp_path)
        result = check_target_exists(args, spec, source_path)
        assert result is False

    def test_target_exists_but_broken_symlink(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test when target exists but is a broken symlink."""
        # Create source structure
        source_path = tmp_path / 'source'
        source_path.mkdir()
        (source_path / 'resources').mkdir()

        # Create broken symlink
        broken_target = tmp_path / 'nonexistent'
        symlink_path = tmp_path / '.mypackage'
        symlink_path.symlink_to(broken_target, target_is_directory=True)

        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
            symlink_name='.mypackage',
        )
        spec = SourceSpec(source_type='package', name='mypackage')

        # Change working directory using monkeypatch
        monkeypatch.chdir(tmp_path)
        result = check_target_exists(args, spec, source_path)
        assert result is False

    def test_force_flag_skips_check(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that force flag bypasses target checking."""
        # Create source structure
        source_path = tmp_path / 'source'
        source_path.mkdir()
        (source_path / 'resources').mkdir()

        # Create symlink pointing to correct location
        symlink_path = tmp_path / '.mypackage'
        symlink_path.symlink_to(
            source_path / 'resources',
            target_is_directory=True,
        )

        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=True,  # Force flag set
            verbose=False,
            symlink_name='.mypackage',
        )
        spec = SourceSpec(source_type='package', name='mypackage')

        # Change working directory using monkeypatch
        monkeypatch.chdir(tmp_path)
        result = check_target_exists(args, spec, source_path)
        assert result is False  # Should not skip even though symlink is correct

    def test_default_symlink_name(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test behavior when symlink_name is None (uses default)."""
        # Create source structure
        source_path = tmp_path / 'source'
        source_path.mkdir()
        (source_path / 'resources').mkdir()

        # Create symlink with default name
        symlink_path = tmp_path / '.mypackage'
        symlink_path.symlink_to(
            source_path / 'resources',
            target_is_directory=True,
        )

        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
            symlink_name=None,  # Should use default .{package_name}
        )
        spec = SourceSpec(source_type='package', name='mypackage')

        # Change working directory using monkeypatch
        monkeypatch.chdir(tmp_path)
        result = check_target_exists(args, spec, source_path)
        assert result is True

    def test_target_resolution_exception(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test when target resolution raises an exception."""
        # Create source structure
        source_path = tmp_path / 'source'
        source_path.mkdir()
        (source_path / 'resources').mkdir()

        # Create symlink pointing to correct location
        symlink_path = tmp_path / '.mypackage'
        symlink_path.symlink_to(
            source_path / 'resources',
            target_is_directory=True,
        )

        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
            symlink_name='.mypackage',
        )
        spec = SourceSpec(source_type='package', name='mypackage')

        # Change working directory using monkeypatch
        monkeypatch.chdir(tmp_path)

        # Remove the symlink target to make it broken
        (source_path / 'resources').rmdir()
        source_path.rmdir()

        result = check_target_exists(args, spec, source_path)
        assert result is False  # Should not skip when resolution fails

    def test_target_exists_exception_during_resolve(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
    ) -> None:
        """Test when target exists but resolve() raises an exception."""
        # Create source structure
        source_path = tmp_path / 'source'
        source_path.mkdir()
        (source_path / 'resources').mkdir()

        # Create symlink
        symlink_path = tmp_path / '.mypackage'
        symlink_path.symlink_to(source_path / 'resources', target_is_directory=True)

        # Mock resolve() to raise an OSError
        mock_resolve = mocker.patch.object(Path, 'resolve')
        mock_resolve.side_effect = OSError('Permission denied')

        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
            symlink_name='.mypackage',
        )
        spec = SourceSpec(source_type='package', name='mypackage')

        # Change working directory using monkeypatch
        monkeypatch.chdir(tmp_path)
        result = check_target_exists(args, spec, source_path)
        assert result is False


class TestResolveAndCreateOperationWithSource:
    """Tests for the new resolve_and_create_operation_with_source function."""

    def test_create_operation_with_resolved_source(
        self,
        tmp_path: Path,
    ) -> None:
        """Test creating operation with already resolved source path."""
        source_path = tmp_path / 'source'
        source_path.mkdir()
        (source_path / 'resources').mkdir()

        args = CliArgs(
            source='mypackage',
            directory='resources',
            dry_run=False,
            force=False,
            verbose=False,
            symlink_name='.mypackage',
        )
        spec = SourceSpec(source_type='package', name='mypackage')

        operation = resolve_and_create_operation_with_source(
            args,
            spec,
            source_path,
        )

        assert isinstance(operation, LinkOperation)
        assert operation.spec == spec
        assert operation.target.source_path == source_path
        assert operation.target.target_directory == 'resources'
        assert operation.target.symlink_name == '.mypackage'
        assert operation.force is False
        assert operation.dry_run is False

    def test_create_operation_with_custom_symlink_name(
        self,
        tmp_path: Path,
    ) -> None:
        """Test creating operation with custom symlink name."""
        source_path = tmp_path / 'source'
        source_path.mkdir()
        (source_path / 'data').mkdir()

        args = CliArgs(
            source='mypackage',
            directory='data',
            dry_run=True,
            force=True,
            verbose=False,
            symlink_name='custom_link',
        )
        spec = SourceSpec(source_type='github', name='repo', org='org')

        operation = resolve_and_create_operation_with_source(
            args,
            spec,
            source_path,
        )

        assert operation.target.target_directory == 'data'
        assert operation.target.symlink_name == 'custom_link'
        assert operation.force is True
        assert operation.dry_run is True
        assert operation.full_source_path == source_path / 'data'


class TestIsSymlinkPointingToCorrectTarget:
    """Tests for the _is_symlink_pointing_to_correct_target helper function."""

    def test_symlink_points_to_correct_target(self, tmp_path: Path) -> None:
        """Test when symlink points to the correct target."""
        # Create target directory
        target_dir = tmp_path / 'target'
        target_dir.mkdir()

        # Create symlink
        symlink_path = tmp_path / 'link'
        symlink_path.symlink_to(target_dir, target_is_directory=True)

        result = _is_symlink_pointing_to_correct_target(symlink_path, target_dir)
        assert result is True

    def test_symlink_points_to_wrong_target(self, tmp_path: Path) -> None:
        """Test when symlink points to the wrong target."""
        # Create two target directories
        correct_target = tmp_path / 'correct'
        correct_target.mkdir()
        wrong_target = tmp_path / 'wrong'
        wrong_target.mkdir()

        # Create symlink pointing to wrong target
        symlink_path = tmp_path / 'link'
        symlink_path.symlink_to(wrong_target, target_is_directory=True)

        result = _is_symlink_pointing_to_correct_target(symlink_path, correct_target)
        assert result is False

    def test_target_is_not_symlink(self, tmp_path: Path) -> None:
        """Test when target exists but is not a symlink."""
        # Create directory (not symlink)
        target_path = tmp_path / 'not_symlink'
        target_path.mkdir()

        expected_target = tmp_path / 'expected'
        expected_target.mkdir()

        result = _is_symlink_pointing_to_correct_target(target_path, expected_target)
        assert result is False
