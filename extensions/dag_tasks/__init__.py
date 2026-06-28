"""
DAG Tasks Extension for pi-coding-agent

A lean unified task manager with DAG dependencies.
Ported from the TypeScript pi-dag-tasks extension.
"""
from .dag_tasks import extension_factory

__all__ = ["extension_factory"]
