"""Tests for pkglink symlink functionality."""

import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from pkglink.symlinks import (
    create_symlink,
    is_managed_link,
    list_managed_links,
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

    @patch('pkglink.symlinks.os')
    def test_supports_symlinks_true(self, mock_os: Mock) -> None:
        """Test that supports_symlinks returns True when os.symlink exists."""
        mock_os.symlink = Mock()
        assert supports_symlinks() is True

    @patch('pkglink.symlinks.os')
    def test_supports_symlinks_false(self, mock_os: Mock) -> None:
        """Test that supports_symlinks returns False when os.symlink doesn't exist."""
        delattr(mock_os, 'symlink')
        assert supports_symlinks() is False


class TestCreateSymlink:
    """Tests for create_symlink function."""

    def test_create_symlink_success(self) -> None:
        """Test successful symlink creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / 'source'
            target = temp_path / 'target'

            source.mkdir()

            # This will either create a symlink or copy depending on system support
            result = create_symlink(source, target)

            assert target.exists()
            assert isinstance(result, bool)

    def test_create_symlink_source_not_exists(self) -> None:
        """Test error when source doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / 'nonexistent'
            target = temp_path / 'target'

            with pytest.raises(
                FileNotFoundError,
                match='Source does not exist',
            ):
                create_symlink(source, target)

    def test_create_symlink_target_exists_no_force(self) -> None:
        """Test error when target exists and force=False."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / 'source'
            target = temp_path / 'target'

            source.mkdir()
            target.touch()

            with pytest.raises(FileExistsError, match='Target already exists'):
                create_symlink(source, target)


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
    def test_is_managed_link(self, case: SymlinkTestCase) -> None:
        """Test is_managed_link function."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            test_path = temp_path / case.name

            if case.is_symlink:
                # Create a dummy target and symlink to it
                target = temp_path / 'target'
                target.mkdir()
                test_path.symlink_to(target)
            else:
                # Create a regular directory
                test_path.mkdir()

            result = is_managed_link(test_path)
            assert result == case.is_managed


class TestListManagedLinks:
    """Tests for list_managed_links function."""

    def test_list_managed_links(self) -> None:
        """Test listing managed links in a directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create some test items
            (temp_path / '.managed1').mkdir()
            (temp_path / '.managed2').mkdir()
            (temp_path / 'not_managed').mkdir()
            (temp_path / 'regular_file.txt').touch()

            result = list_managed_links(temp_path)

            # Should find the two .managed directories
            result_names = {path.name for path in result}
            assert result_names == {'.managed1', '.managed2'}

    def test_list_managed_links_default_cwd(self) -> None:
        """Test listing managed links with default current directory."""
        with patch('pkglink.symlinks.Path.cwd') as mock_cwd:
            mock_dir = Mock()
            mock_cwd.return_value = mock_dir
            mock_dir.iterdir.return_value = []

            result = list_managed_links()

            mock_cwd.assert_called_once()
            assert result == []
