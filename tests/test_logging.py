"""Tests for pkglink logging functionality."""

import logging

from pkglink.logging import (
    configure_logging,
    filter_context_by_prefix,
    format_context_yaml,
    get_logger,
    strip_prefixes_from_keys,
)


class TestFormatContextYaml:
    """Tests for format_context_yaml function."""

    def test_format_context_yaml_empty(self) -> None:
        """Test formatting an empty event dict."""
        result = format_context_yaml({}, indent=0)
        assert result == ''

    def test_format_context_yaml_with_data(self) -> None:
        """Test formatting an event dict with data."""
        event_dict = {'key': 'value', 'number': 42}
        result = format_context_yaml(event_dict, indent=2)

        # Should contain YAML-like output with indentation
        assert 'key: value' in result
        assert 'number: 42' in result
        assert result.startswith('  ')  # Should have indentation

    def test_format_context_yaml_nested(self) -> None:
        """Test formatting nested event dict."""
        event_dict = {
            'simple': 'value',
            '_verbose_data': {'nested': 'content'},
            'normal': 'item',
        }
        result = format_context_yaml(event_dict, indent=0)

        assert 'simple: value' in result
        assert 'normal: item' in result


class TestFilterContextByPrefix:
    """Tests for filter_context_by_prefix function."""

    def test_filter_verbose_prefix(self) -> None:
        """Test filtering _verbose_ prefix in non-verbose mode."""
        event_dict = {
            '_verbose_install_spec': {'name': 'test'},
            'normal_key': 'value',
            '_debug_command': 'data',
            'regular': 'item',
        }

        result = filter_context_by_prefix(event_dict)

        # Verbose and debug keys should be filtered out
        assert '_verbose_install_spec' not in result
        assert '_debug_command' not in result
        # Normal keys should remain
        assert 'normal_key' in result
        assert 'regular' in result
        assert result['normal_key'] == 'value'
        assert result['regular'] == 'item'

    def test_filter_no_prefixes(self) -> None:
        """Test with keys that don't have prefixes to filter."""
        event_dict = {
            'key1': 'value1',
            'key2': 'value2',
        }

        result = filter_context_by_prefix(event_dict)

        assert result == event_dict


class TestStripPrefixesFromKeys:
    """Tests for strip_prefixes_from_keys function."""

    def test_strip_verbose_prefix(self) -> None:
        """Test stripping _verbose_ prefix."""
        event_dict = {
            '_verbose_install_spec': {'name': 'test'},
            'normal_key': 'value',
            '_debug_other': 'data',
            '_perf_timing': 'info',
        }

        result = strip_prefixes_from_keys(event_dict)

        assert 'install_spec' in result
        assert 'other' in result
        assert 'timing' in result
        assert 'normal_key' in result
        assert result['normal_key'] == 'value'

    def test_strip_debug_prefix(self) -> None:
        """Test stripping _debug_ prefix."""
        event_dict = {
            '_debug_command': 'some command',
            'regular': 'value',
        }

        result = strip_prefixes_from_keys(event_dict)

        assert 'command' in result
        assert 'regular' in result
        assert result['regular'] == 'value'

    def test_no_prefix_to_strip(self) -> None:
        """Test with keys that don't have prefixes to strip."""
        event_dict = {
            'key1': 'value1',
            'key2': 'value2',
        }

        result = strip_prefixes_from_keys(event_dict)

        assert result == event_dict


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_configure_logging_verbose(self) -> None:
        """Test configuring logging with verbose=True."""
        # Reset logging configuration
        logging.getLogger().handlers.clear()

        configure_logging(verbose=True)

        # Check that debug level is set
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    def test_configure_logging_non_verbose(self) -> None:
        """Test configuring logging with verbose=False."""
        # Reset logging configuration
        logging.getLogger().handlers.clear()

        configure_logging(verbose=False)

        # Check that info level is set
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_logger(self) -> None:
        """Test that get_logger returns a logger instance."""
        logger = get_logger('test_module')
        assert hasattr(logger, 'info')  # Should be a logger-like object
        assert hasattr(logger, 'error')
        assert hasattr(logger, 'debug')
