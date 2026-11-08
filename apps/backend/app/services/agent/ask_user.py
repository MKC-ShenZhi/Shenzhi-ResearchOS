"""Compatibility alias for the moved Agent ask_user module."""

from importlib import import_module
import sys

sys.modules[__name__] = import_module("app.services.agent.capabilities.ask_user")
