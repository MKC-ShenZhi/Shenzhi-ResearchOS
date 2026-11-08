"""Compatibility alias for the moved Agent workspace module."""

from importlib import import_module
import sys

sys.modules[__name__] = import_module("app.services.agent.extensions.workspace")
