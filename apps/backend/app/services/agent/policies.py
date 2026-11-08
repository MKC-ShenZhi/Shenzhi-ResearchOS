"""Compatibility alias for the moved Agent policies module."""

from importlib import import_module
import sys

sys.modules[__name__] = import_module("app.services.agent.app.policies")
