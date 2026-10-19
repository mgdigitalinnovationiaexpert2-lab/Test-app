"""Providers module: upstream adapter plumbing shared by chat routes."""
from mg_ai.programmer import ProgrammerAdapter
from mg_ai.providers import LiteLLMAdapter, Outcome, Result

__all__ = ["LiteLLMAdapter", "Outcome", "ProgrammerAdapter", "Result"]
