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


def pre_process_log(event_msg: str, event_dict: EventDict) -> tuple[str, str]:
    """Custom log formatting for command execution events.

    Args:
        event_msg: The main event message.
        event_dict: The event dictionary containing additional context.

    Returns:
        The the command to execute and the tool name if available.
    """
    for key in ('timestamp', 'level', 'log_level', 'event'):
        event_dict.pop(key, None)
    return event_msg, ''


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
    event_msg, tool_name = pre_process_log(event_msg, event_dict)
    
    # Check if we're in verbose mode by looking at the root logger level
    verbose_mode = logging.getLogger().level <= logging.DEBUG
    
    # Filter context based on verbose mode
    if not verbose_mode:
        event_dict = filter_context_for_non_verbose(event_msg, event_dict)
    
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
    
    # Only show context YAML in verbose mode
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


def filter_context_for_non_verbose(event_msg: str, event_dict: EventDict) -> EventDict:
    """Filter context dictionary for non-verbose mode to show only essential info."""
    # Define what context to keep for each event type
    essential_context = {
        'starting_pkglink': ['source', 'directory', 'dry_run', 'force'],
        'using_from_option': ['install_package', 'module_name'],
        'parsed_install_spec': ['name', 'source_type'],  # Just basic info, not full dump
        'looking_for_module': ['module'],
        'dry_run_mode': ['directory', 'module_name', 'symlink_name'],
        'resolving_source_path': ['module'],
        'resolved_source_path': ['path'],
        'creating_symlink': ['target', 'source'],
        'target_already_exists': ['target'],
        'source_does_not_exist': ['source'],
        'symlink_created_successfully': [],
        'copy_created_successfully': [],
    }

    # Get the keys we want to keep for this event
    keys_to_keep = essential_context.get(event_msg, [])

    # Special handling for install_spec objects - extract key fields
    if 'install_spec' in event_dict and event_msg == 'parsed_install_spec':
        install_spec = event_dict.get('install_spec', {})
        if isinstance(install_spec, dict):
            # Replace full install_spec with just essential fields
            event_dict.pop('install_spec', None)
            event_dict['name'] = install_spec.get('name')
            event_dict['source_type'] = install_spec.get('source_type')
            if install_spec.get('version'):
                event_dict['version'] = install_spec.get('version')

    # Filter the event_dict to only include essential keys
    if keys_to_keep:
        return {k: v for k, v in event_dict.items() if k in keys_to_keep}

    # For events not in our list, show minimal context or none
    return {}


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
