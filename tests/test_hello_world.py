"""Simple hello world test to get started."""

from pkglink import __version__
from pkglink.cli.main import main


def test_hello_world():
    """Test that we can import and call the main function."""
    # This should not raise an exception
    main()


def test_version_import():
    """Test that we can import the version."""
    assert __version__ == '0.0.0.dev0'
