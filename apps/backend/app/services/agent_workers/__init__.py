"""Execution-side adapters; a distributed worker pool is not started here."""

from .executor import ApplicationWorkerExecutor

__all__ = ['ApplicationWorkerExecutor']
