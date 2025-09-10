import logging

import structlog
import yaml
from rich.console import Console
from rich.syntax import Syntax
from structlog.types import FilteringBoundLogger
from structlog.typing import EventDict

console = Console()

# Type alias for our logger
Logger = FilteringBoundLogger


def format_context_yaml(event_dict: EventDict, indent: int = 2) -> str:
    """Format the context dictionary as YAML.

    Args:
        event_dict: The context dictionary to format.
        indent: The number of spaces to use for indentation.

    Returns:
        The formatted YAML string.
    """
    if not event_dict:
        return ''
    context_yaml = yaml.safe_dump(
        event_dict,
        sort_keys=True,
        default_flow_style=False,
    )
    pad = ' ' * indent
    return '\n'.join(f'{pad}{line}' for line in context_yaml.splitlines())


def pre_process_log(event_msg: str, event_dict: EventDict) -> str:
    """Custom log formatting for command execution events.

    Args:
        event_msg: The main event message.
        event_dict: The event dictionary containing additional context.

    Returns:
        The the command to execute and the tool name if available.
    """
    for key in ('timestamp', 'level', 'log_level', 'event'):
        event_dict.pop(key, None)
    return event_msg


def cli_renderer(
    _logger: Logger,
    method_name: str,
    event_dict: EventDict,
) -> str:
    """Render log messages for CLI output using rich formatting.

    Args:
        logger: The logger instance.
        method_name: The logging method name (e.g., 'info', 'error').
        event_dict: The event dictionary containing log data.

    Returns:
        str: An empty string, as structlog expects a string return but output is printed.
    """
    level = method_name.upper()
    event_msg = event_dict.pop('event', '')
    event_msg = pre_process_log(event_msg, event_dict)

    # Check if we're in verbose mode by looking at the root logger level
    verbose_mode = logging.getLogger().level <= logging.DEBUG

    # Filter context based on verbose mode using prefix approach
    if not verbose_mode:
        event_dict = filter_context_by_prefix(event_dict)

    # Always strip prefixes for clean display
    event_dict = strip_prefixes_from_keys(event_dict)

    context_yaml = format_context_yaml(event_dict)

    # Map log levels to colors/styles
    level_styles = {
        'INFO': 'blue',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'DEBUG': 'magenta',
        'CRITICAL': 'white on red',
        'SUCCESS': 'green',  # for custom use
    }
    # Pick style, fallback to bold cyan for unknown
    style = level_styles.get(level, 'bold cyan')
    log_msg = f'[bold {style}][{level}][/bold {style}] [{style}]{event_msg}[/{style}]'
    console.print(log_msg)

    if context_yaml:
        syntax = Syntax(
            context_yaml,
            'yaml',
            theme='github-dark',
            background_color='default',
            line_numbers=False,
        )
        console.print(syntax)
    return ''  # structlog expects a string return, but we already printed


def filter_context_by_prefix(event_dict: EventDict) -> EventDict:
    """Filter context dictionary based on key prefixes for non-verbose mode.

    Keys starting with '_verbose_' are only shown in verbose mode.
    Keys starting with '_debug_' are only shown in debug mode.
    All other keys are always shown.

    Prefixes are stripped from the keys when displayed.
    """
    # Define prefixes that should be filtered out in non-verbose mode
    filtered_prefixes = ['_verbose_', '_debug_']

    filtered_dict = {}

    for key, value in event_dict.items():
        # Skip keys with filtered prefixes in non-verbose mode
        if any(key.startswith(prefix) for prefix in filtered_prefixes):
            continue
        # Keep all other keys
        filtered_dict[key] = value

    return filtered_dict


def strip_prefixes_from_keys(event_dict: EventDict) -> EventDict:
    """Strip display prefixes from keys for cleaner output."""
    # Define all known prefixes that should be stripped for display
    display_prefixes = ['_verbose_', '_debug_', '_perf_', '_security_']

    cleaned_dict = {}

    for key, value in event_dict.items():
        clean_key = key
        # Remove any matching prefix
        for prefix in display_prefixes:
            if key.startswith(prefix):
                clean_key = key.removeprefix(prefix)
                break

        cleaned_dict[clean_key] = value

    return cleaned_dict


def configure_logging(*, verbose: bool = False) -> None:
    """Configure structlog for pkglink.

    Args:
        verbose: Enable verbose/debug output
    """
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.processors.TimeStamper(fmt='ISO', utc=False),
            structlog.stdlib.add_log_level,
            cli_renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        context_class=dict,
        cache_logger_on_first_use=True,
    )

    if verbose:
        logging.basicConfig(level=logging.DEBUG, handlers=[])
    else:
        logging.basicConfig(level=logging.INFO, handlers=[])


def get_logger(name: str) -> Logger:
    """Get a structured logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)
