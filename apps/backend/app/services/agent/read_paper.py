"""Compatibility alias for the moved Agent read_paper module."""

from importlib import import_module
import sys

sys.modules[__name__] = import_module("app.services.agent.capabilities.read_paper")
