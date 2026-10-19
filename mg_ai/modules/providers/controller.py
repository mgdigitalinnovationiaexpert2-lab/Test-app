"""Providers module: upstream adapter plumbing shared by chat routes.

The LiteLLMAdapter and ProgrammerAdapter clients are constructed by the gateway
composition root (mg_ai.gateway) and injected into the ChatService; this package
exposes them as part of the modular architecture without duplicating logic.
"""
from mg_ai.programmer import ProgrammerAdapter
from mg_ai.providers import LiteLLMAdapter, Outcome, Result

__all__ = ["LiteLLMAdapter", "Outcome", "ProgrammerAdapter", "Result"]
