"""Compatibility alias for the moved Agent fetch_url module."""

from importlib import import_module
import sys

sys.modules[__name__] = import_module("app.services.agent.capabilities.fetch_url")
