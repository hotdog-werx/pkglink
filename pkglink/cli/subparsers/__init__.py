"""Subparser registrations for the unified pkglink CLI."""

import argparse

from . import link, sync, tool


def register_all(subparsers: argparse._SubParsersAction) -> None:
    """Register all pkglink subcommands."""
    link.register(subparsers)
    tool.register(subparsers)
    sync.register(subparsers)
