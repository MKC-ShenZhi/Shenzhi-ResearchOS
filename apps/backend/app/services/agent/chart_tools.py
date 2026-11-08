"""Compatibility alias for the moved Agent chart_tools module."""

from importlib import import_module
import sys

sys.modules[__name__] = import_module("app.services.agent.capabilities.chart_tools")
