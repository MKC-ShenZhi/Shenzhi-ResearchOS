"""Compatibility alias for the moved Agent prompt_templates module."""

from importlib import import_module
import sys

sys.modules[__name__] = import_module("app.services.agent.extensions.prompt_templates")
