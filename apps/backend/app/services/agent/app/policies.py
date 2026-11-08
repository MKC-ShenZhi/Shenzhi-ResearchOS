"""Compatibility alias for the Agent application module."""

from importlib import import_module
import sys

sys.modules[__name__] = import_module("app.services.agent.application.policies")
