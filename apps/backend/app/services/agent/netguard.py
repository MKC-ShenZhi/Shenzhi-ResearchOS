"""Compatibility alias for the moved Agent netguard module."""

from importlib import import_module
import sys

sys.modules[__name__] = import_module("app.integrations.public_web.security")
