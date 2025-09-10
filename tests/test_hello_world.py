"""Basic integration tests for pkglink."""

from pkglink import __version__
from pkglink.parsing import create_parser


def test_version_import() -> None:
    """Test that we can import the version."""
    assert __version__ == '0.0.0.dev0'


def test_cli_parser_creation() -> None:
    """Test that the CLI parser can be created."""
    parser = create_parser()
    assert parser.prog == 'pkglink'


def test_cli_help() -> None:
    """Test that CLI help can be generated without errors."""
    parser = create_parser()
    help_text = parser.format_help()
    assert 'pkglink' in help_text
    assert 'Create symlinks to directories' in help_text
