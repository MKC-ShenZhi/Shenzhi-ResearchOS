"""Compatibility alias for the moved Agent memory module."""

from importlib import import_module
import sys

sys.modules[__name__] = import_module("app.services.agent.execution.memory")
