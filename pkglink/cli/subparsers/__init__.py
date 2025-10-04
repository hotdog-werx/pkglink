"""Subparser registrations for the unified plk CLI."""

import argparse

from . import link, plan, sync, tool


def register_all(subparsers: argparse._SubParsersAction) -> None:
    """Register all plk subcommands."""
    link.register(subparsers)
    tool.register(subparsers)
    plan.register(subparsers)
    sync.register(subparsers)
