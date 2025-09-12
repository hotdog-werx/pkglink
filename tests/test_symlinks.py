"""Tests for pkglink symlink functionality."""

from dataclasses import dataclass
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pkglink import symlinks
from pkglink.symlinks import (
    create_symlink,
    is_managed_link,
    list_managed_links,
    remove_target,
    supports_symlinks,
)


@dataclass
class SymlinkTestCase:
    """Test case for symlink operations."""

    name: str
    is_symlink: bool
    is_managed: bool


class TestSupportsSymlinks:
    """Tests for supports_symlinks function."""

    def test_supports_symlinks_true(self, mocker: MockerFixture) -> None:
        """Test that supports_symlinks returns True when os.symlink exists."""
        mocker.patch.object(symlinks, 'hasattr', return_value=True)
        assert supports_symlinks() is True

    def test_supports_symlinks_false(self, mocker: MockerFixture) -> None:
        """Test that supports_symlinks returns False when os.symlink doesn't exist."""
        mocker.patch.object(symlinks, 'hasattr', return_value=False)
        assert supports_symlinks() is False


class TestCreateSymlink:
    """Tests for create_symlink function."""

    def test_create_symlink_success(self, tmp_path: Path) -> None:
        """Test successful symlink creation."""
        source = tmp_path / 'source'
        target = tmp_path / 'target'

        source.mkdir()

        # This will either create a symlink or copy depending on system support
        result = create_symlink(source, target)

        assert target.exists()
        assert isinstance(result, bool)

    def test_create_symlink_fallback_copy(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test fallback to copy when symlinks are not supported."""
        # Mock supports_symlinks to return False
        mocker.patch('pkglink.symlinks.supports_symlinks', return_value=False)

        source = tmp_path / 'source'
        target = tmp_path / 'target'

        source.mkdir()
        (source / 'test_file.txt').write_text('test content')

        result = create_symlink(source, target)

        # Should return False (indicating copy was used)
        assert result is False
        assert target.exists()
        assert target.is_dir()
        assert not target.is_symlink()
        # Check that content was copied
        assert (target / 'test_file.txt').read_text() == 'test content'

    def test_create_symlink_fallback_copy_file(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test fallback to copy for a file when symlinks are not supported."""
        # Mock supports_symlinks to return False
        mocker.patch('pkglink.symlinks.supports_symlinks', return_value=False)

        source = tmp_path / 'source.txt'
        target = tmp_path / 'target.txt'

        source.write_text('test content')

        result = create_symlink(source, target)

        # Should return False (indicating copy was used)
        assert result is False
        assert target.exists()
        assert target.is_file()
        assert not target.is_symlink()
        # Check that content was copied
        assert target.read_text() == 'test content'

    def test_create_symlink_source_not_exists(self, tmp_path: Path) -> None:
        """Test error when source doesn't exist."""
        source = tmp_path / 'nonexistent'
        target = tmp_path / 'target'

        with pytest.raises(
            FileNotFoundError,
            match='Source does not exist',
        ):
            create_symlink(source, target)

    def test_create_symlink_target_exists_no_force(
        self,
        tmp_path: Path,
    ) -> None:
        """Test error when target exists and force=False."""
        source = tmp_path / 'source'
        target = tmp_path / 'target'

        source.mkdir()
        target.touch()

        with pytest.raises(FileExistsError, match='Target already exists'):
            create_symlink(source, target)


class TestRemoveTarget:
    """Tests for remove_target function."""

    def test_remove_target_symlink(self, tmp_path: Path) -> None:
        """Test removing a symlink with dot prefix."""
        source = tmp_path / 'source'
        target = tmp_path / '.target'  # Use dot prefix

        source.mkdir()
        target.symlink_to(source)

        assert target.exists()
        assert target.is_symlink()

        remove_target(target, expected_name='.target')

        assert not target.exists()

    def test_remove_target_directory(self, tmp_path: Path) -> None:
        """Test removing a directory with dot prefix."""
        target = tmp_path / '.target'  # Use dot prefix

        target.mkdir()
        (target / 'file.txt').write_text('content')

        assert target.exists()
        assert target.is_dir()

        remove_target(target, expected_name='.target')

        assert not target.exists()

    def test_remove_target_file(self, tmp_path: Path) -> None:
        """Test removing a file with dot prefix."""
        target = tmp_path / '.target.txt'  # Use dot prefix

        target.write_text('content')

        assert target.exists()
        assert target.is_file()

        remove_target(target, expected_name='.target.txt')

        assert not target.exists()

    def test_remove_target_refuses_non_dot_prefix(self, tmp_path: Path) -> None:
        """Test that remove_target refuses to remove targets without dot prefix."""
        # Test with directory
        dangerous_dir = tmp_path / 'important_directory'
        dangerous_dir.mkdir()
        (dangerous_dir / 'important_file.txt').write_text('important data')

        with pytest.raises(
            ValueError,
            match='Refusing to remove target without dot prefix',
        ):
            remove_target(
                dangerous_dir,
                expected_name='important_directory',
            )

        # Directory should still exist
        assert dangerous_dir.exists()
        assert (dangerous_dir / 'important_file.txt').exists()

        # Test with file
        dangerous_file = tmp_path / 'important_file.txt'
        dangerous_file.write_text('important data')

        with pytest.raises(
            ValueError,
            match='Refusing to remove target without dot prefix',
        ):
            remove_target(
                dangerous_file,
                expected_name='important_file.txt',
            )

        # File should still exist
        assert dangerous_file.exists()
        assert dangerous_file.read_text() == 'important data'

    def test_remove_target_refuses_name_mismatch(self, tmp_path: Path) -> None:
        """Test that remove_target refuses to remove targets with mismatched names."""
        target_dir = tmp_path / '.mypackage'
        target_dir.mkdir()
        (target_dir / 'test.txt').write_text('test data')

        with pytest.raises(
            ValueError,
            match=r'name mismatch.*Expected "\.different".*got "\.mypackage"',
        ):
            remove_target(target_dir, expected_name='.different')

        # Directory should still exist
        assert target_dir.exists()
        assert (target_dir / 'test.txt').exists()

    @pytest.mark.parametrize(
        ('expected', 'actual'),
        [
            ('.different', '.actual'),
            ('.Actual', '.actual'),
            ('.actual ', '.actual'),
            (' .actual', '.actual'),
            ('.actual-v2', '.actual'),
            ('.act', '.actual'),
        ],
    )
    def test_remove_target_name_mismatch_parametrized(
        self,
        tmp_path: Path,
        expected: str,
        actual: str,
    ):
        actual_file = tmp_path / actual
        actual_file.write_text('test')
        with pytest.raises(ValueError, match='name mismatch'):
            remove_target(actual_file, expected_name=expected)
        assert actual_file.exists()
        assert actual_file.read_text() == 'test'


@pytest.mark.parametrize(
    'target_name',
    [
        '.nonexistent',
        '.weird',
    ],
)
def test_remove_target_nonexistent_or_unrecognized(
    tmp_path: Path,
    target_name: str,
):
    """Test removing a nonexistent or unrecognized target (should not raise)."""
    target = tmp_path / target_name
    # Should not raise, just log a warning
    remove_target(target, expected_name=target_name)
    # File should still not exist
    assert not target.exists()


class TestIsManagedLink:
    """Tests for is_managed_link function."""

    @pytest.mark.parametrize(
        'case',
        [
            SymlinkTestCase(name='.config', is_symlink=True, is_managed=True),
            SymlinkTestCase(name='.myrepo', is_symlink=False, is_managed=True),
            SymlinkTestCase(name='config', is_symlink=True, is_managed=False),
            SymlinkTestCase(
                name='regular_file.txt',
                is_symlink=False,
                is_managed=False,
            ),
        ],
    )
    def test_is_managed_link(
        self,
        case: SymlinkTestCase,
        tmp_path: Path,
    ) -> None:
        """Test is_managed_link function."""
        test_path = tmp_path / case.name

        if case.is_symlink:
            # Create a dummy target and symlink to it
            target = tmp_path / 'target'
            target.mkdir()
            test_path.symlink_to(target)
        else:
            # Create a regular directory
            test_path.mkdir()

        result = is_managed_link(test_path)
        assert result == case.is_managed


class TestListManagedLinks:
    """Tests for list_managed_links function."""

    def test_list_managed_links(self, tmp_path: Path) -> None:
        """Test listing managed links in a directory."""
        (tmp_path / '.managed1').mkdir()
        (tmp_path / '.managed2').mkdir()
        (tmp_path / 'not_managed').mkdir()
        (tmp_path / 'regular_file.txt').touch()

        result = list_managed_links(tmp_path)

        # Should find the two .managed directories
        result_names = {path.name for path in result}
        assert result_names == {'.managed1', '.managed2'}

    def test_list_managed_links_default_cwd(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test listing managed links with default current directory."""
        mock_dir = mocker.Mock()
        mock_dir.iterdir.return_value = []
        mocker.patch.object(Path, 'cwd', return_value=mock_dir)

        result = list_managed_links()

        assert result == []


@pytest.mark.parametrize('kind', ['file', 'dir', 'symlink'])
def test_remove_target_all_types(tmp_path: Path, kind: str):
    """Test remove_target for file, directory, and symlink removal branches."""
    name = '.removeme'
    target = tmp_path / name
    if kind == 'file':
        target.write_text('data')
    elif kind == 'dir':
        target.mkdir()
        (target / 'foo.txt').write_text('bar')
    elif kind == 'symlink':
        real = tmp_path / '.real'
        real.mkdir()
        target.symlink_to(real, target_is_directory=True)
    else:
        msg = f'Unknown kind: {kind}'
        raise ValueError(msg)
    assert target.exists()
    remove_target(target, expected_name=name)
    assert not target.exists()
